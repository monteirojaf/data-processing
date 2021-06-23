import requests
import os
import common
from datetime import date, timedelta
from bag_coronavirus import credentials
import zipfile
import shutil


def file_path():
    return os.path.join(credentials.vmdl_path, credentials.vmdl_file)


def today_string():
    return date.today().strftime('%Y-%m-%d')


def yesterday_string():
    yesterday = date.today() - timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')


def retrieve_vmdl_data():
    print(f'Retrieving vmdl data...')
    payload_token = f'client_id={credentials.vmdl_client_id}&scope={credentials.vmdl_scope}&username={credentials.vmdl_user}&password={credentials.vmdl_password}&grant_type=password'
    headers_token = {'Content-Type': 'application/x-www-form-urlencoded'}
    print(f'Getting OAUTH2 access token...')
    resp_token = requests.request("POST", credentials.vmdl_url_token, headers=headers_token, data=payload_token)
    resp_token.raise_for_status()
    # token_type = resp_token.json()['token_type']
    auth_string = f'Bearer {resp_token.json()["access_token"]}'

    payload_download={}
    headers_download = {'Authorization': auth_string}
    print(f'Downloading data...')
    resp_download = common.requests_get(credentials.vmdl_url_download, headers=headers_download, data=payload_download)
    resp_download.raise_for_status()
    zip_file_path = os.path.join(credentials.vmdl_path, credentials.vmdl_zip_file)
    file_path = os.path.join(credentials.vmdl_path, credentials.vmdl_file)
    print(f'Writing zip data to file {zip_file_path}...')
    # resp_download.encoding = 'utf-8'
    with open(zip_file_path, "wb") as f:
        f.write(resp_download.content)
    print(f'Extracting csv data to file {file_path}...')
    with zipfile.ZipFile(zip_file_path) as z:
        with z.open('data.csv') as zf, open(file_path, 'wb') as f:
            shutil.copyfileobj(zf, f)
    return file_path


def main():
    retrieve_vmdl_data()


if __name__ == "__main__":
    print(f'Executing {__file__}...')
    main()
