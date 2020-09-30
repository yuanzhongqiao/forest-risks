import numpy as np
import pandas as pd
from .. import setup

def fia(store='gcs', states='conus', clean=True, group_repeats=False):
    path = setup.loading(store)

    if states == 'conus':
        states = ['AL','AZ','AR','CA','CO','CT','DE','FL','GA','IA','ID','IL', 
            'IN','KS','KY','LA','ME','MA','MD','MI','MN','MO','MS','MT','NC','ND','NE','NH',
            'NJ','NM','NV','NY','OH','OK','OR','PA','RI','SC','SD','TN','TX', 
            'UT','VT','VA','WA','WV','WI','WY']

    load_state = fia_state_grouped if group_repeats is True else fia_state

    if type(states) is str:
        return load_state(store, states, clean)

    if type(states) is list:
        return pd.concat([load_state(
            store, state, clean
        ) for state in states])

def fia_state(store, state, clean):
    path = setup.loading(store)
    df = pd.read_parquet(path / f'processed/fia-states/long/{state.lower()}.parquet')

    if clean:
        inds = (
            (df['adj_ag_biomass'] > 0) & 
            (df['STDAGE'] < 999) & 
            (df['STDAGE'] > 0) & 
            (~np.isnan(df['FLDTYPCD'])) & 
            (df['FLDTYPCD'] != 999) &
            (df['FLDTYPCD'] != 950) & 
            (df['FLDTYPCD'] <= 983) & 
            (df['DSTRBCD1'] == 0) & 
            (df['COND_STATUS_CD'] == 1) & 
            (df['CONDPROP_UNADJ'] > 0.3) & 
            (df['INVYR'] < 9999) & 
            (df['INVYR'] > 2000)
        )
        df = df[inds]

    df = (
        df
        .rename(columns={
            'LAT': 'lat',
            'LON': 'lon',
            'adj_ag_biomass': 'biomass', 
            'STDAGE': 'age',
            'INVYR': 'year',
            'FLDTYPCD': 'type_code',
        })
        .filter(['lat', 'lon', 'age', 'biomass', 'year', 'type_code'])
    )

    df['state'] = state.upper()

    return df

def fia_state_grouped(store, state, clean):
    path = setup.loading(store)
    df = pd.read_parquet(path / f'processed/fia-states/long/{state.lower()}.parquet')
    df = df.sort_values(['plt_uid', 'CONDID', 'INVYR'])
    df['wide_idx'] = df.groupby(['plt_uid', 'CONDID']).cumcount()
    tmp = []
    for var in [
        'INVYR',
        'adj_balive',
        'adj_mort',
        'fraction_insect',
        'fraction_disease',
        'fraction_fire',
        'fraction_human',
        'disturb_animal',
        'disturb_bugs',
        'disturb_disease',
        'disturb_fire',
        'disturb_human',
        'disturb_weather'
    ]:
        df['tmp_idx'] = var + '_' + df['wide_idx'].astype(str)
        tmp.append(
            df.pivot(index=['plt_uid', 'CONDID'], columns='tmp_idx', values=var)
        )
    wide = pd.concat(tmp, axis=1)
    attrs = df.groupby(['plt_uid', 'CONDID'])[
        ['LAT', 'LON', 'FORTYPCD', 'FLDTYPCD', 'ELEV', 'SLOPE', 'ASPECT']
    ].max()
    return attrs.join(wide).dropna(subset=['INVYR_1'])
