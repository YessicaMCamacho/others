"""
Author: Phyo Thiha
Last Modified Date: 6/18/2017
Script to move new files from an FTP location to another.

NOTE: Assumption made here is that we will store the downloaded
(transferred) files in a local folder. If we choose to delete those
files, we should use something like SQLite to keep track of the
downloaded file names to avoid downloading them again.
"""

import os
import time
import schedule
import pysftp
from ftplib import FTP

from ftp_utils import *

def main():
    TEMP_LOCAL_FOLDER_NAME = 'FTP_Transfer_Temp_Files' # TODO: change this to desired local folder name
    cur_script_file_location = os.path.dirname(os.path.realpath(__file__))

    # For now, we'll store the files in a local folder; later, we can save
    # space by storing just the file names in a local store like SQLite
    local_folder = os.path.join(cur_script_file_location , TEMP_LOCAL_FOLDER_NAME)
    if not os.path.exists(local_folder):
        os.makedirs(local_folder)

    local_files_previously_transferred = [f for f in os.listdir(local_folder) if os.path.isfile(os.path.join(local_folder, f))]

    # Example of FTP_TRANSFER_PARAMS dictionary structure
    FTP_TRANSFER_PARAMS = {'from': {'host':'superpa.in', 'username': 'nielsen', 'pwd': 'FAKEPASSWORD', 'location': '/files'},
                             'to': {'host':'liveftp.groupm.com', 'username': 'TargetInboundFTP', 'pwd': 'FAKEPASSWORD', 'location': '/Target Inbound/DataSources/Nielsen'},}

    # Because we don't want to go through the trouble of setting up the true fingerprint, we'll follow this
    # https://stackoverflow.com/questions/38939454/verify-host-key-with-pysftp
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None
    with pysftp.Connection(host=FTP_TRANSFER_PARAMS['from']['host'],
                           username=FTP_TRANSFER_PARAMS['from']['username'],
                           password=FTP_TRANSFER_PARAMS['from']['pwd'],
                           cnopts=cnopts) as sftp:
        with sftp.cd(FTP_TRANSFER_PARAMS['from']['location']):
            files_and_dirs = sftp.listdir()
            candidate_zip_files = list(filter(lambda x: x[-3:] == 'zip', files_and_dirs))
            files_to_transfer = list(set(candidate_zip_files) - set(local_files_previously_transferred))
            for f in files_to_transfer:
                print("Downloading file from FTP:", f)
                download_from_sftp(sftp, f, local_folder)
        print("All files downloaded to local folder. Commencing upload to destination FTP...")

    with FTP(FTP_TRANSFER_PARAMS['to']['host']) as ftp:
        ftp.login(user = FTP_TRANSFER_PARAMS['to']['username'], passwd = FTP_TRANSFER_PARAMS['to']['pwd'])
        ftp.cwd(FTP_TRANSFER_PARAMS['to']['location'])
        for f in files_to_transfer:
            print("Uploading file to FTP:", f)
            # upload_to_ftp(ftp_obj, source_folder, file_to_upload)
            upload_to_ftp(ftp, local_folder, f)

    # TODO: refactor the ugly joins below
    from_ftp_address = ''.join(['ftp://', FTP_TRANSFER_PARAMS['from']['username'], ':pwd', '@',
                                FTP_TRANSFER_PARAMS['from']['host'], ':default_port/',FTP_TRANSFER_PARAMS['from']['location']])
    to_ftp_address = ''.join(['ftp://', FTP_TRANSFER_PARAMS['to']['username'], ':pwd', '@',
                              FTP_TRANSFER_PARAMS['to']['host'], ':default_port/',FTP_TRANSFER_PARAMS['to']['location']])
    if len(files_to_transfer) > 0:
        print('\n',time.strftime("%c"), '::::> Finished transferring files listed above from ',from_ftp_address, ' => ',
              to_ftp_address)
    else:
        print('\n',time.strftime("%c"), '::::> No new file found to be transffered between ', from_ftp_address, ' and ',
              to_ftp_address)

if __name__ == "__main__":
    print("\n\n*****DO NOT KILL this program::", os.path.basename(__file__) ,"*****\n")
    print("If you accidentally or intentionally killed this program, please rerun it")
    print("This program runs processes every DAY-OF-WEEK at XX:YY EST")

    main()
    # schedule.every().friday.at("6:00").do(main)
    #
    # while True:
    #     schedule.run_pending()
    #     time.sleep(15) # TODO: adjust this parameter based on the size of files to transfer
