import argparse

from mapping_utils import *
from queries import mapped_subcategories_q, unmapped_subcategories_q

import pdb

# Some of the techniques in this script below are derived from:
# REF: http://web.archive.org/web/20190822173629/https://towardsdatascience.com/multi-label-text-classification-with-scikit-learn-30714b7819c5?gi=33423c58a829

DESC = '''
This program guesses subcategory column based on multinomial naive bayes approach. 
To find out how to run, use '-h' flag. Usage example: 
>> python map_subcategories.py -c \"UNITED STATES\"
'''
FEATURE_COLUMNS = ['GM_ADVERTISER_NAME', 'GM_SECTOR_NAME', 'GM_SUBSECTOR_NAME',
                   'GM_CATEGORY_NAME', 'GM_BRAND_NAME', 'GM_PRODUCT_NAME']
TARGET_NAME_COLUMN = 'CP_SUBCATEGORY_NAME'
TARGET_ID_COLUMN = 'CP_SUBCATEGORY_ID'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=DESC)
    parser.add_argument('-c',
                        required=True,
                        type=str,
                        help="(Required) Enter the FULL name of the country as seen under [GM_COUNTRY_NAME] column in "
                             "the GM_CP_MASTER_PRODUCT_MAPPING table. E.g., python map_subcategories.py -c \"UNITED STATES\"")
    parser.add_argument('-m',
                        required=False,
                        type=str,
                        help="(Required) Enter the FULL name (including path) of the model file, "
                             "which contains the model previously (the more recent, the better) trained."
                             "E.g., python map_subcategories.py -m .\output\model_linear_svc_variants_20180920.sav")
    parser.add_argument('-t',
                        required=False,
                        type=str,
                        help="(Optional) Set this flag to '1' if the output file should be in TSV format. Default is xlsx.")
    args = parser.parse_args()

    apac_country = False
    if args.c in APAC_COUNTRIES: # TODO: remove this when we have migrated all APAC countries into main database
        apac_country = True
        TARGET_NAME_COLUMN = 'Global_Subcategory Name'
        TARGET_ID_COLUMN = 'Global_Subcategory ID'

    cur_dir_path = os.path.dirname(os.path.realpath(__file__))
    output_dir = os.path.join(cur_dir_path, OUTPUT_DIR)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print('Loading mapped subcategories from remote database using query:', mapped_subcategories_q, '\n')
    mapped_subcats_df = get_dataframe_from_query(mapped_subcategories_q) # TODO: uncomment this
    # Annoying thing we have to deal with because pandas convert 1 and 0 in the DB to TRUE and FALSE
    mapped_subcats_df['SOS_PRODUCT'] = mapped_subcats_df['SOS_PRODUCT'].astype(int)
    # if you want to save the existing mappings locally (on your computer, uncomment this line and comment out the line above
    # mapped_subcats_df.to_csv(path_or_buf='mapped_subcats.csv', header=True, index=False)
    # mapped_subcats_df = pd.read_csv('mapped_subcats.csv', dtype=str, sep='\t')

    unmapped_subcategories_q += " AND GM_COUNTRY_NAME='" + args.c + "'"
    print('Loading unmapped subcategories for', args.c,
          'from remote database using query:', unmapped_subcategories_q, '\n')
    unmapped_subcats_df = get_dataframe_from_query(unmapped_subcategories_q)
    unmapped_subcats_df['SOS_PRODUCT'] = unmapped_subcats_df['SOS_PRODUCT'].astype(int)

    print('Concatenating and cleaning column data starts:', time.asctime())
    # TODO: creating df_x could become a computational bottleneck; need to find a more efficient way to do it like what I used to do below?
    df_x = (mapped_subcats_df['GM_ADVERTISER_NAME'].astype('str').apply(tokenize)
            + mapped_subcats_df['GM_SECTOR_NAME'].astype('str').apply(tokenize)
            + mapped_subcats_df['GM_SUBSECTOR_NAME'].astype('str').apply(tokenize)
            + mapped_subcats_df['GM_CATEGORY_NAME'].astype('str').apply(tokenize)
            + mapped_subcats_df['GM_BRAND_NAME'].astype('str').apply(tokenize)
            + mapped_subcats_df['GM_PRODUCT_NAME'].astype('str').apply(tokenize)) \
        .apply(' '.join)
    # The line below works similar to above, but it is a bit slower because we need to make sure
    # each column is converted to str(). The upside of this approach is that it is more aligned with
    # functional style programming.
    # df_x = pd.DataFrame(mapped_subcats_df[FEATURE_COLUMNS].apply(lambda x:  ' '.join(str(x)), axis=1).apply(tokenize), columns=['Col'])
    print('Concatenating and cleaning column data ends:', time.asctime())

    label_df, label_id_to_subcat_name, subcat_name_to_subcat_id_ref_table = prepare_label_data(mapped_subcats_df,
                                                                                               'CP_SUBCATEGORY_NAME',#TARGET_NAME_COLUMN,
                                                                                               'CP_SUBCATEGORY_ID')#TARGET_ID_COLUMN)
    tfidf_vectorizer = TfidfVectorizer(
        sublinear_tf=True,  # TODO: we can remove this if log scale doesn't work out
        min_df=1,
        norm='l2', # L2 norm
        encoding='utf-8',
        ngram_range=(1, 2),
        stop_words='english'
    )
    if args.m:
        tfidf_vectorizer.fit_transform(df_x) # we must do this to make vectorizer ready
        model = load_model(args.m)
    else:
        model = fit_linear_svc_model(tfidf_vectorizer.fit_transform(df_x), label_df[[LABEL_ID_COLUMN]])
        write_model(model, os.path.join(output_dir,
                                        ''.join(['model_linear_svc_subcats_', time.strftime('%Y%m%d'), '.sav'])))

    raw_col_names = RAW_COLUMN_NAMES_FOR_APAC if apac_country else RAW_COLUMN_NAMES
    final_col_names = FINAL_COLUMN_NAMES_FOR_APAC if apac_country else RAW_COLUMN_NAMES # all other shares the same keys and vals
    mapped_df = pd.DataFrame(columns=final_col_names, index=None)
    for idx, row in unmapped_subcats_df.iterrows():
        input_str = combine_feature_columns_to_one_long_str(row, FEATURE_COLUMNS)
        predicted_subcat_name = predict_using_svc(input_str,
                                                  model,
                                                  tfidf_vectorizer,
                                                  label_id_to_subcat_name)
        predicted_subcat_id =  subcat_name_to_subcat_id_ref_table[predicted_subcat_name]

        row_headers = row.to_dict().keys()
        vals_of_interest = [row[c] if c in row_headers else '' for c in raw_col_names]
        vals_with_adjusted_col_names = dict(zip(final_col_names, vals_of_interest))
        mapped_df.loc[len(mapped_df)] = prepare_row_content(
                                            row,
                                            # 'MAPPING_PROCESS_TYPE' ,'GM_GLOBAL_PRODUCT_ID', 'GM_COUNTRY_ID' , 'GM_COUNTRY_NAME', 'GM_ADVERTISER_NAME', 'GM_SECTOR_NAME', 'GM_SUBSECTOR_NAME', 'GM_CATEGORY_NAME'
                                            raw_col_names,
                                            # 'Included', 'CategoryType', 'Local_Section', 'Local_Category', 'Local_Advertiser', 'Local_Brand', 'Local_Product'
                                            final_col_names,
                                            predicted_subcat_name,
                                            predicted_subcat_id,
                                            TARGET_NAME_COLUMN, #'Global_Subcategory Name' OR 'CP_SUBCATEGORY_NAME'
                                            TARGET_ID_COLUMN, # 'Global_Subcategory ID' OR 'CP_SUBCATEGORY_ID'
                                            apac_country)
        # print(sorted(mapped_df.columns.tolist()))
        # print(sorted(shit.keys()))
        # import pdb
        # pdb.set_trace()
        # print('Finished')

        # python map_subcategories.py -c "INDIA" -m .\output\model_linear_svc_subcats_20181023.sav
        # mapped_df.loc[len(mapped_df)] = prepare_row_content(row,
        #                                                     # 'MAPPING_PROCESS_TYPE' ,'GM_GLOBAL_PRODUCT_ID', 'GM_COUNTRY_ID' , 'GM_COUNTRY_NAME', 'GM_ADVERTISER_NAME', 'GM_SECTOR_NAME', 'GM_SUBSECTOR_NAME', 'GM_CATEGORY_NAME'
        #                                                     raw_col_names,
        #                                                     # 'Included', 'CategoryType', 'Local_Section', 'Local_Category', 'Local_Advertiser', 'Local_Brand', 'Local_Product'
        #                                                     final_col_names,
        #                                                     predicted_subcat_name,
        #                                                     predicted_subcat_id,
        #                                                     TARGET_NAME_COLUMN, #'Global_Subcategory Name' OR 'CP_SUBCATEGORY_NAME'
        #                                                     TARGET_ID_COLUMN, # 'Global_Subcategory ID' OR 'CP_SUBCATEGORY_ID'
        #                                                     apac_country)

    write_to_file(mapped_df, 'mapped_subcategories_', args.t)

