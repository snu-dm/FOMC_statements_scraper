import pandas as pd
from sqlalchemy import create_engine, select, delete, insert, update
import config
import dateutil.parser
import os
from glob import glob
from tqdm import tqdm
from schemas import statements

#Create Engine
engine = create_engine(f'postgresql://{config.user}:{config.pw}@{config.host}:{config.port}/{config.db}')


# save_temp_dir = './temp'
# if not os.path.exists(save_temp_dir): os.makedirs(save_temp_dir)

def extract_begin_end_dates(date_range):
    if '-' not in date_range:
        return dateutil.parser.parse(date_range), dateutil.parser.parse(date_range)
    else:
        date_range = date_range.replace(',', '')
        try:
            month, dates, year = date_range.split(' ')
            dates = dates.split('-')
            begin_date = dateutil.parser.parse(' '.join([dates[0], month, year]))
            end_date = dateutil.parser.parse(' '.join([dates[1], month, year]))
        except:
            date_range = date_range.replace('-', ' ')
            begin_date_month, bigin_date_date, end_date_month, end_date_date, year = date_range.split(' ')
            begin_date = dateutil.parser.parse(' '.join([bigin_date_date, begin_date_month, year]))
            end_date = dateutil.parser.parse(' '.join([end_date_date, end_date_month, year]))
        return begin_date, end_date
    
def get_insert_query(document_date, meeting_date_start, meeting_date_end):
    insert_query = insert(statements).values(
        path='disclosures/FOMC/{}/{}.parquet'.format(document_date[:4], document_date),
        organization = 'FOMC',
        documentdate = document_date,
        meetingdate_start = meeting_date_start,
        meetingdate_end = meeting_date_end
    )
    return insert_query

if __name__ == '__main__':
    
    data_filepaths = glob('./Statements/no_stop-phrases/*/*')
    print('Number of documents: {}'.format(len(data_filepaths)))
    
    with engine.connect() as con:
    
        for filepath in tqdm(data_filepaths):
            with open(filepath, encoding='utf-8-sig') as f: 
                line_list = f.readlines()
            document_date = os.path.basename(filepath).replace('.txt', '')
            meeting_date = line_list[0].replace('\n', '').replace('MEETING_DATE: ', '')
            document = line_list[1]

            transactions = con.begin()
            try:
                meeting_date_start, meeting_date_end = extract_begin_end_dates(meeting_date)

                # PostgreSQL 
                insert_query = get_insert_query(document_date, meeting_date_start, meeting_date_end)
                con.execute(insert_query)

                # S3 (MINIO)
        #         df = pd.DataFrame([(document_date, meeting_date_start, meeting_date_end, document)], \
        #                           columns=['documentdate', 'meetingdate_start', 'meetingdate_end', 'document'])
        #         save_filepath = os.path.join(save_temp_dir, '{}.parquet'.format(document_date))
        #         df.to_parquet(save_filepath)

                transactions.commit()
            except:
                print('Failed to INSERT data: {}'.format(filepath))
                transactions.rollback()
                
    # REMOVE TEMP directory
