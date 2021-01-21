import sys
import common
from ods_publish import credentials
import time
import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

ods_dataset_uids = sys.argv[1].split(',')
count = len(ods_dataset_uids)
print('Publishing ODS datasets...')
for i, dataset_uid in enumerate(ods_dataset_uids):
    common.publish_ods_dataset(dataset_uid, credentials)
    if i < (count-1):
        print('Waiting 5 seconds before sending next publish request to ODS...')
        time.sleep(5)

print('Job successful!')