import os
import io
import logging
import pandas as pd
import datetime
import xml.etree.ElementTree as ET

import common
from staka_kantonsblatt import credentials


# References:
# https://www.amtsblattportal.ch/docs/api/


def main():
    # process the last pages or every available article?
    process_everything = False
    if process_everything:
        df = iterate_over_years()
        path_export = os.path.join(credentials.data_path, 'export', '100352_kantonsblatt.csv')
        df.to_csv(path_export, index=False)
        common.update_ftp_and_odsp(path_export, 'staka_kantonsblatt', '100352')
        return
    iterate_over_newest_pages()


def iterate_over_newest_pages(pages=10):
    base_url = 'https://kantonsblatt.ch/api/v1/publications/csv?publicationStates=PUBLISHED&cantons=BS'
    url = f'{base_url}&pageRequest.page=0'
    for page in range(pages):
        logging.info(f'Getting data from {url}...')
        r = common.requests_get(url)
        r.raise_for_status()
        df_curr_page = pd.read_csv(io.StringIO(r.content.decode('utf-8')), sep=';')
        df_curr_page = add_columns(df_curr_page)
        common.ods_realtime_push_df(df_curr_page, credentials.push_url)
        url = f'{base_url}&pageRequest.page={page+1}'


def iterate_over_years():
    start_year = 2019
    df = pd.DataFrame()
    for year in range(start_year, datetime.datetime.now().year + 1):
        for month in range(1, 13):
            if year == datetime.datetime.now().year and month > datetime.datetime.now().month:
                break
            logging.info(f'Getting data for {year}-{month}...')
            df_month = iterate_over_pages(year, month)
            df = pd.concat([df, df_month])
    return df


def iterate_over_pages(year, month):
    base_url = f'https://kantonsblatt.ch/api/v1/publications/csv?publicationStates=PUBLISHED&cantons=BS'
    start_date = f'&publicationDate.start={year}-{month}-01'
    end_date = f'&publicationDate.end={year}-{month+1}-01' if month < 12 else f'&publicationDate.end={year+1}-01-01'
    url = f'{base_url}{start_date}{end_date}'
    page = 0
    next_page = f'{url}&pageRequest.page={page}'
    df = pd.DataFrame()
    while True:
        logging.info(f'Getting data from {next_page}...')
        r = common.requests_get(next_page)
        r.raise_for_status()
        df_curr_page = pd.read_csv(io.StringIO(r.content.decode('utf-8')), sep=';')
        if df_curr_page.empty:
            break
        df_curr_page = add_columns(df_curr_page)
        common.ods_realtime_push_df(df_curr_page, credentials.push_url)
        df = pd.concat([df, df_curr_page])
        page = page + 1
        next_page = f'{url}&pageRequest.page={page}'
    return df


def add_columns(df):
    df['url_kantonsblatt'] = df['id'].apply(lambda x: f'https://www.kantonsblatt.ch/#!/search/publications/detail/{x}')
    df['url_pdf'] = df['id'].apply(lambda x: f'https://www.kantonsblatt.ch/api/v1/publications/{x}/pdf')
    df['url_xml'] = df['id'].apply(lambda x: f'https://www.kantonsblatt.ch/api/v1/publications/{x}/xml')
    df['content'] = ''
    df['attachments'] = ''
    for index, row in df.iterrows():
        xml_content = get_content_from_xml(row['url_xml'])
        root = ET.fromstring(xml_content)
        content = root.find('content')
        attach = root.find('attachments')
        df.at[index, 'content'] = ET.tostring(content, encoding='utf-8') if content is not None else ''
        df.at[index, 'attachments'] = ET.tostring(attach, encoding='utf-8') if attach is not None else ''
    return df


def get_content_from_xml(url):
    r = common.requests_get(url)
    r.raise_for_status()
    return r.text


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
    logging.info("Job successful!")
