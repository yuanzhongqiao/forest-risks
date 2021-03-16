import warnings

import numpy as np
import xarray as xr
from astropy.convolution import Gaussian2DKernel, convolve


def scramble_2d(img, phase=None):
    """
    Scramble a 2d dataset
    """
    img = img.copy()
    nan_inds = np.isnan(img)
    img[nan_inds] = 0
    F = np.fft.fft2(img)
    F_mag = np.abs(np.fft.fftshift(F))
    F_phase = np.angle(np.fft.fftshift(F))
    if phase is not None:
        Fnew_phase = phase
    else:
        Fnew_phase = 2.0 * np.pi * np.random.rand(F_phase.shape[0], F_phase.shape[1])
    Fnew = F_mag * np.exp(1j * Fnew_phase)
    fnew = np.fft.ifft2(np.fft.ifftshift(Fnew))
    fnew = np.real(fnew)
    fnew[nan_inds] = np.NaN
    return fnew


def scramble_3d(data):
    """
    Scramble a 3d time x space dataset
    """
    data = data.copy()
    nt = data.shape[0]
    for t in range(nt):
        data[t] = scramble_2d(data[t])
    return data


def smooth(da, gaussian_stddev=1):
    """
    Smooth in space a data array according
    to box with height and width of `spatial_smoothing_window`
    """
    # define kernel size
    kernel = Gaussian2DKernel(x_stddev=gaussian_stddev)
    # blur your maps according to that kernel
    blur = convolve(da.values, kernel)
    return xr.DataArray(blur, coords=da.coords)


def fire(
    full_climate,
    nftd,
    mtbs=None,
    eval_only=False,
    scramble=False,
    add_local_climate_trends=False,
    rolling_period=None,
    gaussian_kernel_size=None,
):
    """
    Prepare x and y and group variables for fire model fitting
    given an xarray dataset
    """
    if rolling_period is not None:
        climate = full_climate.sel(time=rolling_period)
    else:
        print('here we define climate')
        climate = full_climate
    shape = (len(climate.time), len(climate.y), len(climate.x))
    if scramble:
        x = np.asarray([scramble_3d(climate[var].values).flatten() for var in climate.data_vars]).T
        f = np.asarray([np.tile(scramble_2d(a), [shape[0], 1, 1]).flatten() for a in nftd.values]).T
    else:
        x = np.asarray([climate[var].values.flatten() for var in climate.data_vars]).T
        f = np.asarray([np.tile(a, [shape[0], 1, 1]).flatten() for a in nftd.values]).T

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=RuntimeWarning)
        if rolling_period is not None:
            print('Doing the global averages on a rolling basis')

            # if rolling_period is set, you'll exchange out the `climate` variable
            # with a new rolling_averaged one for this part
            # climate is not called again after this
            f2 = np.asarray(
                [
                    np.asarray(
                        [
                            np.tile(a, [shape[1], shape[2]])
                            for a in climate['tmean']
                            .rolling(dim={'time': 12}, min_periods=12, center=False)
                            .max()
                            .sel(time=rolling_period)
                            .mean(dim=['x', 'y'])
                        ]
                    ).flatten(),
                    np.asarray(
                        [
                            np.tile(a, [shape[1], shape[2]])
                            for a in climate['ppt']
                            .rolling(dim={'time': 12}, min_periods=12, center=False)
                            .sum()
                            .sel(time=rolling_period)
                            .mean(dim=['x', 'y'])
                        ]
                    ).flatten(),
                ]
            ).T

        else:
            print('Doing the global averages on a groupby basis')

            f2 = np.asarray(
                [
                    np.asarray(
                        [
                            np.tile(a.mean(), [12, shape[1], shape[2]])
                            for a in climate['tmean'].groupby('time.year').max()
                        ]
                    ).flatten(),
                    np.asarray(
                        [
                            np.tile(a.mean(), [12, shape[1], shape[2]])
                            for a in climate['ppt'].groupby('time.year').sum()
                        ]
                    ).flatten(),
                ]
            ).T

        if add_local_climate_trends:
            if rolling_period is not None:
                print('Doing the local averages on a rolling basis')
                f3 = np.asarray(
                    # if we want to do some coarsening/smoothing we'll add that here
                    [
                        np.asarray(
                            [climate['tmean'].rolling(dim={'time': 12}, center=False).max()]
                        ).flatten(),
                        np.asarray(
                            [climate['ppt'].rolling(dim={'time': 12}, center=False).sum()]
                        ).flatten(),
                    ]
                ).T
            else:
                print('Doing the local averages on a groupby basis')
                if gaussian_kernel_size is not None:
                    print('Using gaussian kernel of width {} std dev'.format(gaussian_kernel_size))
                    f3 = np.asarray(
                        [
                            np.asarray(
                                [
                                    np.tile(
                                        smooth(a, gaussian_stddev=gaussian_kernel_size), [12, 1, 1]
                                    )
                                    for a in climate['tmean'].groupby('time.year').max()
                                ]
                            ).flatten(),
                            np.asarray(
                                [
                                    np.tile(
                                        smooth(a, gaussian_stddev=gaussian_kernel_size), [12, 1, 1]
                                    )
                                    for a in climate['ppt'].groupby('time.year').sum()
                                ]
                            ).flatten(),
                        ]
                    ).T
                else:
                    print('Using local info')

                    f3 = np.asarray(
                        [
                            np.asarray(
                                [
                                    np.tile(a, [12, 1, 1])
                                    for a in climate['tmean'].groupby('time.year').max()
                                ]
                            ).flatten(),
                            np.asarray(
                                [
                                    np.tile(a, [12, 1, 1])
                                    for a in climate['ppt'].groupby('time.year').sum()
                                ]
                            ).flatten(),
                        ]
                    ).T
    if gaussian_kernel_size:
        print('Tacking together x, f')

        x = np.concatenate([x, f], axis=1)
    else:
        print('Tacking together x, f, f2')

        x = np.concatenate([x, f, f2], axis=1)
    if add_local_climate_trends and gaussian_kernel_size:
        print('Tacking on f3 to everything')
        x = np.concatenate([x, f3], axis=1)

    if eval_only:
        return x

    else:
        y = mtbs['monthly'].values.flatten()
        return x, y, f3


def drought(df, eval_only=False, duration=10):
    """
    Prepare x and y values for drought model fitting
    given a data frame
    """
    df = df.copy()

    if eval_only:
        fit_vars = ['ppt_sum_min', 'tavg_mean_max', 'age', 'age_squared', 'duration']
        df['age_squared'] = df['age'] ** 2
        df['duration'] = duration
        x = df[fit_vars]
        x = x.values
        meta = df[['lat', 'lon', 'type_code']].reset_index(drop=True)

        return x, meta

    else:
        fit_vars = ['ppt_sum_min_1', 'tavg_mean_max_1', 'age', 'age_squared', 'duration']
        # 'pdsi_mean_min_1','cwd_sum_max_1',
        # 'pet_mean_max_1', 'vpd_mean_max_1',
        inds = (
            (df['condprop'] > 0.3)
            & (not (df['disturb_human_1'] is True))
            & (not (df['disturb_fire_1'] is True))
            & (not (df['treatment_cutting_1'] is True))
        )
        df = df[inds].copy()
        df['age_squared'] = df['age'] ** 2
        df['duration'] = df['year_1'] - df['year_0']
        y = df['mort_1'] / df['balive_0']
        x = df[fit_vars]

        inds = (np.isnan(x).sum(axis=1) == 0) & (~np.isnan(y)) & (y < 1)

        meta = df[inds][['lat', 'lon', 'type_code']].reset_index(drop=True)

        x = x[inds].values
        y = y[inds].values

        return x, y, meta


def insects(df, eval_only=False, duration=10):
    """
    Prepare x and y values for insect model fitting
    given a data frame
    """
    df = df.copy()

    if eval_only:
        fit_vars = ['ppt_sum_min', 'tavg_mean_max', 'age', 'age_squared', 'duration']
        df['age_squared'] = df['age'] ** 2
        df['duration'] = duration
        x = df[fit_vars]
        x = x.values
        meta = df[['lat', 'lon', 'type_code']].reset_index(drop=True)

        return x, meta

    else:

        fit_vars = [
            'ppt_sum_min_1',
            'tavg_mean_max_1',
            'age',
            'age_squared',
            'duration',
        ]
        # 'pdsi_mean_min_1','cwd_sum_max_1',
        # 'pet_mean_max_1', 'vpd_mean_max_1',
        inds = (
            (df['condprop'] > 0.3)
            & (not (df['disturb_human_1'] is True))
            & (not (df['disturb_fire_1'] is True))
            & (not (df['treatment_cutting_1'] is True))
        )
        df = df[inds].copy()
        df['age_squared'] = df['age'] ** 2
        df['duration'] = df['year_1'] - df['year_0']
        y = df['fraction_insect_1'] * (df['mort_1'] / df['balive_0'])
        x = df[fit_vars]

        inds = (np.isnan(x).sum(axis=1) == 0) & (~np.isnan(y)) & (y < 1)

        meta = df[inds][['lat', 'lon', 'type_code']].reset_index(drop=True)

        x = x[inds].values
        y = y[inds].values

        return x, y, meta
