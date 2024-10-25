import os
import xml.etree.ElementTree as ET
import pandas as pd
from owslib.wfs import WebFeatureService
from fgi_geodatenshop import credentials
import geopandas as gpd 
import logging
import io
import sys
import common
import requests
from datetime import datetime
from common import change_tracking as ct


# Create new ‘Title’ column in df_wfs (Kanton Basel-Stadt WMS/**Hundesignalisation**/Hundeverbot)
def extract_second_hier_name(row, df2):
    # Search in df2 for the matching name
    matching_row = df2[df2['Name'] == row['Name']]
    if not matching_row.empty:
        hier_name = matching_row['Hier_Name'].values[0]
        hier_parts = hier_name.split('/')
        return hier_parts[1] if len(hier_parts) > 1 else None


# Function for retrieving and parsing WMS GetCapabilities
def get_wms_capabilities(url_wms):
    response = requests.get(url=url_wms, verify=False)
    xml_data = response.content
    root = ET.fromstring(xml_data)
    namespaces = {'wms': 'http://www.opengis.net/wms'}
    return root, namespaces


# Recursive function to traverse the layer hierarchy and save the paths
def extract_layers(layer_element, namespaces, data, name_hierarchy=None, title_hierarchy=None):
    # Find the name and title of the current layer
    name_element = layer_element.find("wms:Name", namespaces)
    title_element = layer_element.find("wms:Title", namespaces)

    layer_name = name_element.text if name_element is not None else None
    layer_title = title_element.text if title_element is not None else None

    # If the layer has a name and a title, set up the hierarchy path
    if layer_name is not None and layer_title is not None:
        # Update the hierarchy path
        current_name_hierarchy = f"{name_hierarchy}/{layer_name}" if name_hierarchy else layer_name
        current_title_hierarchy = f"{title_hierarchy}/{layer_title}" if title_hierarchy else layer_title

        # Check whether there are sub-layers
        sublayers = layer_element.findall("wms:Layer", namespaces)

        if sublayers:
            # If there are sublayers, go through them recursively
            for sublayer in sublayers:
                extract_layers(sublayer, namespaces, data, current_name_hierarchy, current_title_hierarchy)
        else:
            # If there are no sub-layers, add the deepest layer to the data
            data.append([layer_name, layer_title, current_name_hierarchy, current_title_hierarchy])


# Main function to process WMS data and create a DataFrame
def process_wms_data(url_wms):
    root, namespaces = get_wms_capabilities(url_wms)
    capability_layer = root.find(".//wms:Capability/wms:Layer", namespaces)

    # Initialize the data list outside the recursive function
    data = []
    if capability_layer is not None:
        extract_layers(capability_layer, namespaces, data)
        df_wms = pd.DataFrame(data, columns=['Name', 'Layer', 'Hier_Name', 'Hier_Titel'])
    return df_wms


# Function for retrieving and parsing WFS GetCapabilities
def process_wfs_data(url_wfs):
    wfs = WebFeatureService(url=url_wfs, version='2.0.0')
    # Retrieve the list of available layers (feature types) and their metadata
    feature_list = []
    for feature in wfs.contents:
        feature_info = wfs[feature]
        feature_list.append({
         'Name': feature,
         'Metadata URL': feature_info.metadataUrls})
    # Convert to DataFrame and display
    df_wfs = pd.DataFrame(feature_list)
    # Clearing the column 'Layer Name' ( remove 'ms:')
    df_wfs['Name'] = df_wfs['Name'].str.replace('ms:', '', regex=False)
    # Clean-up of the ‘Metadata URL’ column (remove prefix and suffix)
    df_wfs['Metadata URL'] = df_wfs['Metadata URL'].astype(str)
    df_wfs['Metadata URL'] = df_wfs['Metadata URL'].str.replace(r"\[{'url': '", '', regex=True)
    df_wfs['Metadata URL'] = df_wfs['Metadata URL'].str.replace(r"'}\]", '', regex=True)
    return df_wfs


# Function to create Map_links
def create_map_links(geometry):
    # check whether the data is a geo point or geo shape
    logging.info(f'the type of the geometry is {geometry.geom_type}')
   # geometry_types = gdf.iloc[0][geometry].geom_type
    if geometry.geom_type == 'Polygon':
        centroid = geometry.centroid
    else:
         centroid = geometry

     #  create a Map_links
    lat, lon = centroid.y, centroid.x
    Map_links = f'https://opendatabs.github.io/map-links/?lat={lat}&lon={lon}'
    return Map_links


no_file_copy = False
if 'no_file_copy' in sys.argv:
    no_file_copy = True
    logging.info('Proceeding without copying files...')
else:
    logging.info('Proceeding with copying files...')


def remove_empty_string_from_list(string_list):
    return list(filter(None, string_list))   


# Returns value from geocat
def geocat_value(key, metadata):
    if str(key) != '':
        pathlist = key.split('.')
        tmp = metadata
        for x in pathlist:
            if isinstance(tmp, list):
                tmp = tmp[0]  # Take the first element if tmp is a list
            tmp = tmp[int(x) if x.isdigit() else x]
        return tmp
    else:
        return ''


def geocat_try(geocat_path_list, metadata):
    for key in geocat_path_list:
        try:
            return geocat_value(key, metadata)
        except (KeyError, TypeError):
            # This key apparently is not present, try the next one in the list
            pass
    logging.info('Error: None of the given keys exist in the source dict...')
    raise KeyError(';'.join(geocat_path_list))


# Function for saving FGI geodata for each layer name
def save_geodata_for_layers(wfs, df_fgi, file_path):
    meta_data = pd.read_excel(os.path.join(credentials.path_harv, 'Metadata.xlsx'), na_filter=False)
    metadata_for_ods = []
    logging.info('Iterating over datasets...')
    for index, row in meta_data.iterrows():
        if row['import']:
        # Which shapes need to be imported to ods?
            shapes_to_load = remove_empty_string_from_list(row['Layers'].split(';'))
            num_files = len(shapes_to_load)
            if num_files == 0:  # load all shapes.
                # find the list of shapes in fgi_list
                ind_list = df_fgi[df_fgi['Titel'] == row['Titel']].index
                shapes_to_load = df_fgi.iloc[ind_list]['Name'].values[0]
            gdf_result = gpd.GeoDataFrame()
            for shapefile in shapes_to_load:
            # Retrieve and save the geodata for each layer name in shapes_to_load
                response = wfs.getfeature(typename=shapefile)
                gdf = gpd.read_file(io.BytesIO(response.read()))
                gdf_result = pd.concat([gdf_result, gdf])

            # creat a maps_urls
            if row['create_map_urls']:
                logging.info(f"Create Map urls for {row['titel_nice']}")
                gdf_result = gdf_result.to_crs(epsg=4326)
                gdf_result['Map Links'] = \
                gdf_result.apply(lambda row2: create_map_links(row2['geometry']), axis=1, result_type='expand')

            # save the geofile locally
            titel = row['Titel']
            titel_dir = os.path.join(file_path, titel)
            os.makedirs(titel_dir, exist_ok=True)
            file_name = f'{row['titel_nice']}.gpkg'
            geopackage_file = os.path.join(titel_dir, file_name)
            gdf_result.to_file(geopackage_file, driver='GPKG')
            # save in ftp server
            ftp_remote_dir = 'harvesters/GVA/data'
            common.upload_ftp(geopackage_file, credentials.ftp_server, credentials.ftp_user, credentials.ftp_pass,
                                       ftp_remote_dir)
            # In some geocat URLs there's a tab character, remove it.
            geocat_uid = row['geocat'].rsplit('/', 1)[-1].replace('\t', '')
            geocat_url = f'https://www.geocat.ch/geonetwork/srv/api/records/{geocat_uid}'
            logging.info(f'Getting metadata from {geocat_url}...')
            r = common.requests_get(geocat_url, headers={'accept': 'application/xml, application/json'})
            r.raise_for_status()
            metadata = r.json()
            # modified = datetime.strptime(str(row['dateaktualisierung']), '%Y%m%d').date().strftime("%Y-%m-%d")
            ods_id = row['ods_id']
            schema_file = ''
            if row['schema_file']:
                schema_file = f'{ods_id}.csv'

            # Geocat dataset descriptions are in lists if given in multiple languages. Let's assume that the German text is always the first element in the list.
            geocat_description_textgroup = \
                metadata['gmd:identificationInfo']['che:CHE_MD_DataIdentification']['gmd:abstract']['gmd:PT_FreeText'][
                    'gmd:textGroup']
            geocat_description = geocat_description_textgroup[0]['gmd:LocalisedCharacterString'][
                '#text'] if isinstance(geocat_description_textgroup, list) else \
                geocat_description_textgroup['gmd:LocalisedCharacterString']['#text']
            # Check if a description to the current shape is given in Metadata.csv
            description = row['beschreibung']
            dcat_ap_ch_domain = ''
            if str(row['dcat_ap_ch.domain']) != '':
                dcat_ap_ch_domain = str(row['dcat_ap_ch.domain'])

            # Add entry to harvester file
            metadata_for_ods.append({
                'ods_id': ods_id,
                'name': geocat_uid + ':' + row['titel_nice'],
                'title': row['titel_nice'],
                'description': description if len(description) > 0 else geocat_description,
                # Only add nonempty strings as references
                'references': '; '.join(filter(None, [row['mapbs_link'], row['geocat'], row['referenz']])),
                # str(row['mapbs_link']) + '; ' + str(row['geocat']) + '; ' + str(row['referenz']) + '; ',
                'theme': str(row['theme']),
                'keyword': str(row['keyword']),
                'dcat_ap_ch.domain': dcat_ap_ch_domain,
                'dcat_ap_ch.rights': 'NonCommercialAllowed-CommercialAllowed-ReferenceRequired',
                'dcat.contact_name': 'Fachstelle für OGD Basel-Stadt',
                'dcat.contact_email': 'opendata@bs.ch',
                # 'dcat.contact_name': geocat_value(row['geocat_contact_firstname']) + ' ' + geocat_value(row['geocat_contact_lastname']),
                # 'dcat.contact_name': geocat_try(['gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact.che:CHE_CI_ResponsibleParty.che:individualFirstName.gco:CharacterString.#text',
                #                                  'gmd:distributionInfo.gmd:MD_Distribution.gmd:distributor.gmd:MD_Distributor.gmd:distributorContact.che:CHE_CI_ResponsibleParty.che:individualFirstName.gco:CharacterString.#text'])
                #                      + ' '
                #                      + geocat_try(['gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact.che:CHE_CI_ResponsibleParty.che:individualLastName.gco:CharacterString.#text',
                #                                    'gmd:distributionInfo.gmd:MD_Distribution.gmd:distributor.gmd:MD_Distributor.gmd:distributorContact.che:CHE_CI_ResponsibleParty.che:individualLastName.gco:CharacterString.#text']),
                # 'dcat.contact_email': geocat_value(row['geocat_email']),
                # 'dcat.contact_email': geocat_try(['gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact.che:CHE_CI_ResponsibleParty.gmd:contactInfo.gmd:CI_Contact.gmd:address.che:CHE_CI_Address.gmd:electronicMailAddress.gco:CharacterString.#text',
                #                                   'gmd:distributionInfo.gmd:MD_Distribution.gmd:distributor.gmd:MD_Distributor.gmd:distributorContact.che:CHE_CI_ResponsibleParty.gmd:contactInfo.gmd:CI_Contact.gmd:address.che:CHE_CI_Address.gmd:electronicMailAddress.gco:CharacterString.#text',
                #                                   'gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact[0].che:CHE_CI_ResponsibleParty.gmd:contactInfo.gmd:CI_Contact.gmd:address.che:CHE_CI_Address.gmd:electronicMailAddress.gco:CharacterString.#text']),
                # 'dcat.created': geocat_value('geocat_created'),
                'dcat.created': geocat_try([
                    'gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:citation.gmd:CI_Citation.gmd:date.gmd:CI_Date.gmd:date.gco:DateTime.#text',
                    'gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:citation.gmd:CI_Citation.gmd:date.gmd:CI_Date.gmd:date.gco:Date.#text'], metadata),
                'dcat.creator': geocat_try([
                    'gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact.che:CHE_CI_ResponsibleParty.che:individualFirstName.gco:CharacterString.#text',
                    'gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact.1.che:CHE_CI_ResponsibleParty.che:individualFirstName.gco:CharacterString.#text',
                    'gmd:distributionInfo.gmd:MD_Distribution.gmd:distributor.gmd:MD_Distributor.gmd:distributorContact.che:CHE_CI_ResponsibleParty.che:individualFirstName.gco:CharacterString.#text'], metadata),
                'dcat.accrualperiodicity': row['dcat.accrualperiodicity'],
                'attributions': 'Geodaten Kanton Basel-Stadt',
                # For some datasets, keyword is a list
                # 'keyword': isinstance(metadata["gmd:identificationInfo"]["che:CHE_MD_DataIdentification"]["gmd:descriptiveKeywords"][0]["gmd:MD_Keywords"]["gmd:keyword"], list)
                # if metadata["gmd:identificationInfo"]["che:CHE_MD_DataIdentification"]["gmd:descriptiveKeywords"][0]["gmd:MD_Keywords"]["gmd:keyword"][0]["gco:CharacterString"]["#text"]
                # else metadata["gmd:identificationInfo"]["che:CHE_MD_DataIdentification"]["gmd:descriptiveKeywords"][0]["gmd:MD_Keywords"]["gmd:keyword"]["gco:CharacterString"]["#text"],
                'publisher': row['herausgeber'],
                'dcat.issued': row['dcat.issued'],
                #'modified': modified,
                'language': 'de',
                'publizierende-organisation': row['publizierende_organisation'],
                # Concat tags from csv with list of fixed tags, remove duplicates by converting to set, remove empty string list comprehension
                'tags': ';'.join([i for i in list(set(row['tags'].split(';') + ['opendata.swiss'])) if i != '']),
                'geodaten-modellbeschreibung': row['modellbeschreibung'],
                'source_dataset': 'https://data-bs.ch/opendatasoft/harvesters/GVA/data/' + file_name,
                'schema_file': schema_file
            })

    # Save harvester file
    if len(metadata_for_ods) > 0:
        ods_metadata = pd.concat([pd.DataFrame(), pd.DataFrame(metadata_for_ods)], ignore_index=True, sort=False)
        ods_metadata_filename = os.path.join(credentials.data_path, 'Opendatasoft_Export_GVA_GPKG.csv')
        ods_metadata.to_csv(ods_metadata_filename, index=False, sep=';')

    if ct.has_changed(ods_metadata_filename) and (not no_file_copy):
        logging.info(f'Uploading ODS harvester file {ods_metadata_filename} to FTP Server...')
        common.upload_ftp(ods_metadata_filename, credentials.ftp_server, credentials.ftp_user, credentials.ftp_pass,
                            'harvesters/GVA')
        ct.update_hash_file(ods_metadata_filename)

    # Upload each schema_file
    logging.info('Uploading ODS schema files to FTP Server...')

    for schemafile in ods_metadata['schema_file'].unique():
        if schemafile != '':
            schemafile_with_path = os.path.join(credentials.schema_path, schemafile)
            if ct.has_changed(schemafile_with_path) and (not no_file_copy):
                logging.info(f'Uploading ODS schema file to FTP Server: {schemafile_with_path}...')
                common.upload_ftp(schemafile_with_path, credentials.ftp_server, credentials.ftp_user,
                                  credentials.ftp_pass, 'harvesters/GVA')
                ct.update_hash_file(schemafile_with_path)
    else:
        logging.info('Harvester File contains no entries, no upload necessary.')


def main():
    url_wms = 'https://wms.geo.bs.ch/?SERVICE=wms&REQUEST=GetCapabilities'
    url_wfs = 'https://wfs.geo.bs.ch/'
    
    df_wms = process_wms_data(url_wms)
    df_wfs = process_wfs_data(url_wfs)
    
    df_wfs['Titel'] = df_wfs.apply(lambda row: extract_second_hier_name(row, df_wms), axis=1)
    new_column_order = ['Titel', 'Name', 'Metadata URL']
    df_wfs = df_wfs[new_column_order]
    df_wms_not_in_wfs = df_wms[~df_wms['Name'].isin(df_wfs['Name'])]
    # assign the layer names under main names to collect the geodata
    df_fgi = df_wfs.groupby('Titel')['Name'].apply(list).reset_index()

    # save DataFrames in CSV files
    data_path = credentials.data_path
    df_wms.to_csv(os.path.join(data_path, 'Hier_wms.csv'), sep=';', index=False)
    df_fgi.to_csv(os.path.join(data_path, 'FGI_List.csv'), sep=';', index=False)
    df_wms_not_in_wfs.to_csv(os.path.join(data_path, 'wms_not_in_wfs.csv'), sep=';', index=False)
    path_export = os.path.join(data_path, '100395.csv')
    df_wfs.to_csv(path_export, sep=';', index=False)
    common.update_ftp_and_odsp(path_export, 'FST-OGD', '100395')


    wfs = WebFeatureService(url=url_wfs, version='2.0.0')
    file_path = os.path.join(credentials.data_path, 'export')
    save_geodata_for_layers(wfs, df_fgi, file_path)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.info(f'Executing {__file__}...')
    main()
    logging.info('Job successful!')