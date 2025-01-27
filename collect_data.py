import logging
import os
import requests
import utils
import logger_helper
import json
import hashlib
import sqlite3

version_hash = utils.try_get_version_hash()

logger = logger_helper.get_logger(logging.INFO)
session = requests.Session()

METADATA_TEMPLATE = utils.get_b64_data(b'aHR0cHM6Ly95b3N0YXItc2VydmVyaW5mby5ibHVlYXJjaGl2ZXlvc3Rhci5jb20ve30uanNvbg==')
A_BUNDLE_CATALOG_TEMPLATE = utils.get_b64_data(b'e30vQW5kcm9pZC9idW5kbGVEb3dubG9hZEluZm8uanNvbg==')
A_BUNDLE_BASE_TEMPLATE = utils.get_b64_data(b'e30vQW5kcm9pZC8=')
I_BUNDLE_CATALOG_TEMPLATE = utils.get_b64_data(b'e30vaU9TL2J1bmRsZURvd25sb2FkSW5mby5qc29u')
I_BUNDLE_BASE_TEMPLATE = utils.get_b64_data(b'e30vaU9TLw==')
BINARY_CATALOG_TEMPLATE = utils.get_b64_data(b'e30vTWVkaWFSZXNvdXJjZXMvTWVkaWFDYXRhbG9nLmpzb24=')
BINARY_BASE_TEMPLATE = utils.get_b64_data(b'e30vTWVkaWFSZXNvdXJjZXMv')
TABLE_CATALOG_TEMPLATE = utils.get_b64_data(b'e30vVGFibGVCdW5kbGVzL1RhYmxlQ2F0YWxvZy5qc29u')
TABLE_BASE_TEMPLATE = utils.get_b64_data(b'e30vVGFibGVCdW5kbGVzLw==')

RAW_BASE_PATH = os.path.join(os.path.dirname(__file__), 'raw')
BUNDLE_FILES_DIR = os.path.join(RAW_BASE_PATH, version_hash, 'bundles')
BINARY_FILES_DIR = os.path.join(RAW_BASE_PATH, version_hash, 'binary')
CATALOG_FILES_DIR = os.path.join(RAW_BASE_PATH, version_hash, 'catalogs')
TABLE_FILES_DIR = os.path.join(RAW_BASE_PATH, 'table')
dirs = [BUNDLE_FILES_DIR, BINARY_FILES_DIR, TABLE_FILES_DIR, CATALOG_FILES_DIR]
for d in dirs:
    os.makedirs(d, exist_ok=True)


def collect_bundle_files(base_url: str, full_json: dict):
    con = sqlite3.connect(utils.DATABASE_NAME)
    dl_dict = full_json[utils.get_b64_data(b'QnVuZGxlRmlsZXM=')]
    bundle_base_url = A_BUNDLE_BASE_TEMPLATE.format(base_url)
    success_cnt, skip_cnt, total_cnt, progress_cnt = 0, 0, len(dl_dict), 0
    cur = con.cursor()
    for bundle_data in dl_dict:
        progress_cnt += 1
        table_row_data = cur.execute(
            "SELECT * FROM bundle_dict WHERE FILE_NAME=(?) AND CRC=(?)",
            (bundle_data['Name'], bundle_data['Crc'])
        ).fetchone()
        if not table_row_data:
            save_path = os.path.join(BUNDLE_FILES_DIR, bundle_data['Name'])
            logger.debug(f'collecting bundle file: {bundle_data["Name"]} ...')
            data = session.get(f'{bundle_base_url}{bundle_data["Name"]}').content
            with open(save_path, 'wb') as f:
                f.write(data)
            cur.execute('''
                INSERT INTO bundle_dict (FILE_ID, FILE_FULL_PATH, SIZE, CRC, FILE_NAME, UPDATE_TIME, VERSION_MARK)
                 VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (None, save_path, bundle_data['Size'], bundle_data['Crc'], bundle_data['Name'], utils.get_cur_time(), version_hash))
            con.commit()
            logger.info(f'({success_cnt+skip_cnt}/{total_cnt}) bundle file: {bundle_data["Name"]} collected.')
            success_cnt += 1
        else:
            logger.debug(f'bundle file: {bundle_data["Name"]} skipped.')
            skip_cnt += 1
    logger.info(f'Task of collecting bundle files has finished.')
    logger.info(f'success: {success_cnt}, skipped: {skip_cnt}')
    logger.info(''.join(['=' for _ in range(100)]))
    con.close()
    return success_cnt, skip_cnt, total_cnt

def cmp_table_row_data(all_data):
    def no_current_binary_key(item):
        binary_data = item[1]
        for line in all_data:
            crc = line[4]
            filename = line[7]
            if crc == binary_data['Crc'] and filename == binary_data['fileName']:
                return False
        return True
    return no_current_binary_key

def collect_binary_files(base_url: str, full_json: dict):
    con = sqlite3.connect(utils.DATABASE_NAME)
    dl_dict = full_json[utils.get_b64_data(b'VGFibGU=')]
    binary_base_url = BINARY_BASE_TEMPLATE.format(base_url)
    cur = con.cursor()
    all_data = cur.execute("SELECT * FROM binary_dict").fetchall()
    rest_binary_data = list(filter(cmp_table_row_data(all_data), dl_dict.items()))
    success_cnt, skip_cnt, total_cnt, progress_cnt = 0, len(dl_dict) - len(rest_binary_data), len(rest_binary_data), 0

    for item in rest_binary_data:
        progress_cnt += 1
        binary_data = item[1]
        save_path = f'{BINARY_FILES_DIR}/{binary_data["path"]}'
        save_dir = os.path.dirname(save_path)
        if not os.path.exists(save_dir):
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
        logger.debug(f'collecting binary file: {binary_data["fileName"]} ...')
        data = session.get(f'{binary_base_url}{binary_data["path"]}').content
        with open(save_path, 'wb') as f:
            f.write(data)
        cur.execute('''
            INSERT INTO binary_dict (FILE_ID, FILE_FULL_PATH, SOURCE_FILE_PATH, SIZE, CRC, BYTES, MIDIA_TYPE, FILE_NAME, UPDATE_TIME, VERSION_MARK)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (None, save_path, binary_data['path'], binary_data['bytes'], binary_data['Crc'], binary_data['bytes'], binary_data['mediaType'], binary_data['fileName'], utils.get_cur_time(), version_hash))
        con.commit()
        logger.info(f'({success_cnt+skip_cnt}/{total_cnt}) binary file: {binary_data["fileName"]} collected.')
        success_cnt += 1

    logger.info(f'Task of collecting binary files has finished.')
    logger.info(f'success: {success_cnt}, skipped: {skip_cnt}')
    logger.info(''.join(['=' for _ in range(100)]))
    con.close()
    return success_cnt, skip_cnt, total_cnt


def collect_table_files(base_url: str, full_json: dict):
    con = sqlite3.connect(utils.DATABASE_NAME)
    dl_dict = full_json[utils.get_b64_data(b'VGFibGU=')]
    table_base_url = TABLE_BASE_TEMPLATE.format(base_url)
    success_cnt, skip_cnt, total_cnt, progress_cnt = 0, 0, len(dl_dict), 0
    cur = con.cursor()
    for table_name in dl_dict:
        progress_cnt += 1
        table_data = dl_dict[table_name]
        save_path = os.path.join(TABLE_FILES_DIR, table_name)
        table_row_data = cur.execute(
            "SELECT * FROM table_dict WHERE FILE_NAME=(?) AND CRC=(?)",
            (table_data['Name'], table_data['Crc'])
        ).fetchone()
        if not table_row_data:
            logger.debug(f'collecting table: {table_name} ...')
            data = session.get(f'{table_base_url}{table_name}').content
            with open(save_path, 'wb') as f:
                f.write(data)
            cur.execute('''
                INSERT INTO table_dict (FILE_ID, FILE_FULL_PATH, SIZE, CRC, FILE_NAME, UPDATE_TIME, VERSION_MARK)
                 VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (None, save_path, table_data['Size'], table_data['Crc'], table_name, utils.get_cur_time(), version_hash))
            con.commit()
            logger.info(f'({success_cnt+skip_cnt}/{total_cnt}) table file: {table_name} collected.')
            success_cnt += 1
        else:
            logger.debug(f'table file: {table_name} skipped.')
            skip_cnt += 1
    logger.info(f'Task of collecting table files has finished.')
    logger.info(f'success: {success_cnt}, skipped: {skip_cnt}')
    logger.info(''.join(['=' for _ in range(100)]))
    con.close()
    return success_cnt, skip_cnt, total_cnt


def check_and_create_catalog_file(catalog_type: str, catalog_file_name: str, catalog_json: dict, con: sqlite3.Connection):
    json_md5 = hashlib.md5(json.dumps(catalog_json).encode()).hexdigest()
    logger.debug(f'{catalog_type} type catalog\'s md5 is: {json_md5}')
    catalog_full_path = con.execute(
        '''SELECT CATALOG_FULL_PATH FROM catalog_dict
         WHERE CATALOG_TYPE=(?) AND CATALOG_MD5=(?)
         ORDER BY UPDATE_TIME DESC''',
        (catalog_type, json_md5)
    ).fetchone()
    if (not catalog_full_path) or (catalog_full_path and not os.path.exists(catalog_full_path[0])):
        file_full_path = os.path.join(CATALOG_FILES_DIR, f'{catalog_file_name}.json')
        if os.path.exists(file_full_path):
            file_full_path = os.path.join(
                CATALOG_FILES_DIR,
                f'{catalog_file_name}_{utils.get_cur_time()}.json'
            )
        logger.debug(f'create new catalog file: {file_full_path}')
        with open(file_full_path, 'w') as catalog_file:
            catalog_file.write(json.dumps(catalog_json, indent=4))
        con.execute('''
            INSERT INTO catalog_dict (CATALOG_ID, CATALOG_TYPE, CATALOG_FULL_PATH, CATALOG_MD5, UPDATE_TIME, VERSION_MARK)
             VALUES (?, ?, ?, ?, ?, ?)
        ''', (None, catalog_type, file_full_path, json_md5, utils.get_cur_time(), version_hash))
        con.commit()
        logger.info(f'Newest {catalog_type} type catalog collected.')
    else:
        logger.info(f'Newest {catalog_type} type catalog file exists, skip.')


def collect_all_catalogs(use_local_file=False):
    con = sqlite3.connect(utils.DATABASE_NAME)
    cur = con.cursor()
    # collect main catalog
    main_catalog_json, file_source = utils.get_newest_catalog('MAIN', cur, METADATA_TEMPLATE.format(version_hash), session, use_local_file)
    if file_source == 'remote':
        check_and_create_catalog_file('MAIN', 'main-catalog', main_catalog_json, con)
    base_url = utils.get_base_from_json(main_catalog_json)

    # collect child catalogs
    bundle_catalog_json, file_source = utils.get_newest_catalog('BUN', cur, A_BUNDLE_CATALOG_TEMPLATE.format(base_url), session, use_local_file)
    if file_source == 'remote':
        check_and_create_catalog_file('BUN', 'bundle-catalog', bundle_catalog_json, con)

    binary_catalog_json, file_source = utils.get_newest_catalog('BIN', cur, BINARY_CATALOG_TEMPLATE.format(base_url), session, use_local_file)
    if file_source == 'remote':
        check_and_create_catalog_file('BIN', 'binary-catalog', binary_catalog_json, con)

    table_catalog_json, file_source = utils.get_newest_catalog('TABLE', cur, TABLE_CATALOG_TEMPLATE.format(base_url), session, use_local_file)
    if file_source == 'remote':
        check_and_create_catalog_file('TABLE', 'table-catalog', table_catalog_json, con)

    con.close()
    logger.info(''.join(['=' for _ in range(100)]))
    return base_url, bundle_catalog_json, binary_catalog_json, table_catalog_json


if __name__ == '__main__':
    if version_hash:
        global_base_url, bundle_json, bin_json, table_json = collect_all_catalogs(use_local_file=True)
        collect_bundle_files(global_base_url, bundle_json)
        collect_binary_files(global_base_url, bin_json)
        collect_table_files(global_base_url, table_json)
        logger.info('All files have been collect.')
    else:
        logger.error('please set version hash first.')
