import logging
import datetime
from datetime import timezone
from zoneinfo import ZoneInfo
import numpy
import pandas as pd
import common
from smarte_strasse_schall import credentials
from requests.auth import HTTPBasicAuth


def main():
    auth = HTTPBasicAuth(credentials.username, credentials.password)
    df_vehicles = push_vehicles(auth)
    # df_sound_levels = push_sound_levels(auth)
    pass


def push_vehicles(auth):
    now = datetime.datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/Zurich'))
    end = now.isoformat()
    start = (now - datetime.timedelta(hours=6)).isoformat()
    r = common.requests_get(url=credentials.url + 'api/vehicle-detections', params={'start_time': start, 'size': '10000'}, auth=auth)
    r.raise_for_status()
    json = r.json()
    df = pd.json_normalize(json, record_path='results')
    df_vehicles = df[['localDateTime', 'classification']].copy(deep=True)
    # todo: Retrieve real values for speed and sound level as soon as API provides them
    df_vehicles['speed'] = numpy.NAN
    df_vehicles['level'] = numpy.NAN
    df_vehicles['timestamp_text'] = df_vehicles.localDateTime
    common.ods_realtime_push_df(df_vehicles, credentials.ods_dataset_url, credentials.ods_push_key, credentials.ods_api_key)
    # {
    #     "localDateTime": "2022-01-19T08:17:13.896+01:00",
    #     "classification": "UNKNOWN",
    #     "timestamp_text": "2022-01-19T08:17:13.896+01:00",
    #     "speed": 49.9,
    #     "level": 50.1
    # }
    return df_vehicles


# todo: Implement as soon as API is ready.
def push_sound_levels(auth):
    now = datetime.datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/Zurich'))
    end = now.isoformat()
    start = (now - datetime.timedelta(hours=6)).isoformat()
    r = common.requests_get(url=credentials.url + 'api/sound-levels', auth=auth, params={'start_time': start, 'size': '10000'})
    # r = common.requests_get(url=credentials.url + 'api/sound-levels/aggs/avg', auth=auth, params={'start_time': start, 'size': '10000'})
    r.raise_for_status()
    json = r.json()
    df = pd.json_normalize(json, record_path='results')
    df_sound_levels = ''
    pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.info(f'Executing {__file__}...')
    main()