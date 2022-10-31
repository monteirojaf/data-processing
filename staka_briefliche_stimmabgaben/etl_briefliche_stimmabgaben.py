import pandas as pd
from staka_briefliche_stimmabgaben import credentials, update_page
import common
from common import change_tracking as ct
import logging
import os
import glob
from datetime import datetime
import numpy as np


def main():
    logging.info('get previous data, starting from 07-03-2021')
    df_publ = get_previous_data_from_20210307()
    logging.info('get file and date of latest available file')
    latest_file, datetime_abst = get_latest_file_and_date()
    date_abst = str(datetime_abst.date())
    # to do: check if this is the date of currently active Abstimmung...
    dates = [str(x.date()) for x in df_publ['abstimmungsdatum']]
    logging.info('check if data from latest Abstimmung is already in the df, if not add it')
    if date_abst not in dates:
        logging.info(f'Add data of currently active Abstimmung of {date_abst}')
        df_latest = make_df_for_publ(latest_file=latest_file, datetime_abst=datetime_abst)
        df_publ = pd.concat([df_latest, df_publ], ignore_index=True)
    logging.info('make df for visualisation')
    df_viz, data_missing_from = make_df_for_visualization(df=df_publ.copy())
    logging.info('remove 0-entries for now available data')
    remove_old_zero_entries(df=df_viz)
    # make date columns of string type
    df_publ['datum'] = df_publ['datum'].dt.strftime('%Y-%m-%d')
    df_publ['abstimmungsdatum'] = [str(x) for x in df_publ['abstimmungsdatum']]

    # upload csv files
    logging.info('upload csv files of the two dataframes')
    df_publ.to_csv(credentials.path_export_file_publ, index=False)
    df_viz.to_csv(credentials.path_export_file_viz, index=False)

    # push df_publ
    if ct.has_changed(credentials.path_export_file_publ):
        ct.update_hash_file(credentials.path_export_file_publ)
        logging.info("push data to ODS realtime API")
        logging.info("push for dataset 100223")
        push_url = credentials.ods_live_realtime_push_url_publ
        push_key = credentials.ods_live_realtime_push_key_publ
        common.ods_realtime_push_df(df_publ, url=push_url, push_key=push_key)
    # push df_viz
    if ct.has_changed(credentials.path_export_file_viz):
        ct.update_hash_file(credentials.path_export_file_viz)
        logging.info("push data to ODS realtime API")
        logging.info("push for dataset 100224")
        push_url = credentials.ods_live_realtime_push_url_viz
        push_key = credentials.ods_live_realtime_push_key_viz
        common.ods_realtime_push_df(df_viz, url=push_url, push_key=push_key)
        logging.info("update page with visualisation")
        update_page.main(data_missing_from=data_missing_from)

def get_previous_data_from_20210307():
    pattern = '????????_Eingang_Stimmabgaben*morgen.xlsx'
    file_list = glob.glob(os.path.join(credentials.path_stimmabgaben, pattern))
    df_all = pd.DataFrame()
    for file in file_list:
        datetime_abst = os.path.basename(file).split("_", 1)[0]
        datetime_abst = datetime.strptime(datetime_abst, '%Y%m%d')
        df = make_df_for_publ(latest_file=file, datetime_abst=datetime_abst)
        df_all = pd.concat([df_all, df], ignore_index=True)
    return df_all


def get_latest_file_and_date():
    pattern = '????????_Eingang_Stimmabgaben*.xlsx'
    data_file_names = []
    file_list = glob.glob(os.path.join(credentials.path_stimmabgaben, pattern))
    if len(file_list) > 0:
        latest_file = max(file_list, key=os.path.getmtime)
        data_file_names.append(os.path.basename(latest_file))
    datetime_abst = data_file_names[0].split("_", 1)[0]
    datetime_abst = datetime.strptime(datetime_abst, '%Y%m%d')
    return latest_file, datetime_abst


def make_df_for_publ(latest_file, datetime_abst):
    columns = ['tag', 'datum', 'eingang_pro_tag', 'eingang_kumuliert', 'stimmbeteiligung']
    df_stimmabgaben = pd.read_excel(latest_file,
                                    sheet_name=0,
                                    header=None,
                                    names=columns,
                                    skiprows=6
                                    )
    df_stimmabgaben['stimmbeteiligung'] = 100 * df_stimmabgaben['stimmbeteiligung']
    # add column Abstimmungsdatum
    df_stimmabgaben["abstimmungsdatum"] = datetime_abst
    # remove empty rows
    df_stimmabgaben = df_stimmabgaben.dropna()
    return df_stimmabgaben


def make_df_for_visualization(df):
    # df['tage_bis_abst'] = [(datetime_abst - d0).days for d0 in df['datum']]
    df['tage_bis_abst'] = df['abstimmungsdatum'] - df['datum']
    df['tage_bis_abst'] = [x.days for x in df['tage_bis_abst']]
    df['stimmbeteiligung_vis'] = [round(x, 1) if not np.isnan(x) else 0.0 for x in
                                  df['stimmbeteiligung']]
    df_stimmabgaben_vis = pd.DataFrame()
    df_stimmabgaben_vis[['datum', 'stimmbeteiligung', 'abstimmungsdatum', 'tage_bis_abst']] \
        = df[['datum', 'stimmbeteiligung_vis', 'abstimmungsdatum', 'tage_bis_abst']]
    df_stimmabgaben_vis = df_stimmabgaben_vis[df.tage_bis_abst.isin([18, 11, 6, 5, 4, 3, 2, 1])]
    # add dates with tage_bis_abst in [18, 11, 6, 5, 4, 3, 2, 1]
    data_missing_from = -1
    for abst_datum in df.abstimmungsdatum.unique():
        df_abst = df_stimmabgaben_vis[df_stimmabgaben_vis.abstimmungsdatum == abst_datum]
        for i in [18, 11, 6, 5, 4, 3, 2, 1, 0]:
            if i not in df_abst.tage_bis_abst.values.astype(int):
                data_missing_from = max(i, data_missing_from)
                s = pd.DataFrame([[abst_datum-np.timedelta64(i, 'D'), 0.0, abst_datum, i]],
                                 columns=['datum', 'stimmbeteiligung', 'abstimmungsdatum', 'tage_bis_abst'])
                df_stimmabgaben_vis = pd.concat([df_stimmabgaben_vis, s])
    # change format of datum, abstimmungsdatum
    df_stimmabgaben_vis['datum'] = df_stimmabgaben_vis['datum'].dt.strftime('%Y-%m-%d')
    df_stimmabgaben_vis['abstimmungsdatum'] = [str(x) for x in df_stimmabgaben_vis['abstimmungsdatum']]
    return df_stimmabgaben_vis, data_missing_from

def remove_old_zero_entries(df):
    # obtain all entries with stimmbeteiliging = 0.0 (remove auth once dataset is public)
    req = common.requests_get(
        f'https://data.bs.ch/api/v2/catalog/datasets/100224/exports/json?refine=stimmbeteiligung:{0.0}&limit=-1&offset=0&timezone=UTC',
        auth=(credentials.username, credentials.password))
    file = req.json()
    df_zero = pd.DataFrame.from_dict(file)
    # remove those records for which there is now an entry, i.e. those 0-entries that are not in df_stimmabgaben_vis
    common_rows = pd.merge(df_zero, df, how='inner')
    to_delete = df_zero.subtract(common_rows, axis='columns')
    payload = to_delete.to_json(orient="records")
    delete_url = credentials.ods_live_realtime_delete_url_viz
    push_key = credentials.ods_live_realtime_push_key_viz
    r = common.requests_post(url=delete_url, data=payload, params={'pushkey': push_key})
    r.raise_for_status()

# Realtime API bootstrap data df_publ:
# {
# "tag": "Mittwoch",
#      "datum": "2022-05-15",
#      "eingang_pro_tag" : 1,
#      "eingang_kumuliert" : 1,
#     "stimmbeteiligung": 1.0,
#      "abstimmungsdatum": "2022-05-15"
# }

# Realtime API bootstrap data df_vis:
# {
#     "datum": "2022-05-15",
#     "stimmbeteiligung": 1.0,
#     "abstimmungsdatum": "2022-05-15",
#      "tage_bis_abst": 1
# }


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.info(f'Executing {__file__}...')
    main()
