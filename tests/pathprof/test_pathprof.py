#!/usr/bin/env python
# -*- coding: utf-8 -*-

# from __future__ import absolute_import
# from __future__ import division
# from __future__ import print_function
# from __future__ import unicode_literals

import os
# we need to modify the SRTM search path, such that the tests can find
# the hgt file in the test directory;
# DO NOT change lon and lat coordinates to lie outside of the hgt tile
this_dir, _ = os.path.split(__file__)
os.environ['SRTMDATA'] = os.path.join(this_dir, 'srtm')

import pytest
from functools import partial
import numpy as np
from numpy.testing import assert_equal, assert_allclose
from astropy.tests.helper import assert_quantity_allclose
from astropy import units as apu
from astropy.units import Quantity
from pycraf import conversions as cnv
from pycraf import pathprof
from pycraf.helpers import check_astro_quantities
from astropy.utils.misc import NumpyRNGContext
import json
from itertools import product
import h5py


TOL_KWARGS = {'atol': 1.e-4, 'rtol': 1.e-4}


class TestPropagation:

    def setup(self):

        # TODO: add further test cases

        self.lon_t, self.lat_t = 6.5 * apu.deg, 50.5 * apu.deg
        self.lon_r, self.lat_r = 6.6 * apu.deg, 50.75 * apu.deg
        self.hprof_step = 100 * apu.m

        self.omega = 0. * apu.percent
        self.temperature = (273.15 + 15.) * apu.K  # as in Excel sheet
        self.pressure = 1013. * apu.hPa

        self.cases = list(
            # freq, (h_tg, h_rg), time_percent, version, (G_t, G_r)
            product(
                [0.1, 1., 10.],
                [(50, 50), (200, 200)],
                [2, 10, 50],
                [14, 16],
                [(0, 0), (20, 30)],
            ))

        self.pprop_template = os.path.join(
            this_dir, 'cases',
            'pprop_{:.2f}ghz_{:.2f}m_{:.2f}m_{:.2f}percent_v{:d}.json'
            )
        self.loss_template = os.path.join(
            this_dir, 'cases',
            'loss_{:.2f}ghz_{:.2f}m_{:.2f}m_{:.2f}percent_'
            '{:.2f}db_{:.2f}db_v{:d}.json'
            )
        self.fastmap_template = os.path.join(
            this_dir, 'fastmap',
            'attens_{:.2f}ghz_{:.2f}m_{:.2f}m_{:.2f}percent_v{:d}.hdf5'
            )
        self.pprops = []
        for case in self.cases:

            freq, (h_tg, h_rg), time_percent, version, (G_t, G_r) = case

            pprop = pathprof.PathProp(
                freq * apu.GHz,
                self.temperature, self.pressure,
                self.lon_t, self.lat_t,
                self.lon_r, self.lat_r,
                h_tg * apu.m, h_rg * apu.m,
                self.hprof_step,
                time_percent * apu.percent,
                version=version,
                )
            self.pprops.append(pprop)

            # Warning: if uncommenting, the test cases will be overwritten
            # do this only, if you need to update the json files
            # (make sure, that results are correct!)
            # pprop_name = self.pprop_template.format(
            #     freq, h_tg, h_rg, time_percent, version
            #     )
            # json.dump(pprop._pp, open(pprop_name, 'w'))

            los_loss = pathprof.freespace_loss(pprop)
            trop_loss = pathprof.troposcatter_loss(
                pprop, G_t * cnv.dB, G_r * cnv.dB,
                )
            duct_loss = pathprof.ducting_loss(pprop)
            diff_loss = pathprof.diffraction_loss(pprop)

            tot_loss = pathprof.complete_loss(
                pprop, G_t * cnv.dB, G_r * cnv.dB,
                )

            losses = {}
            losses['L_bfsg'] = los_loss[0].to(cnv.dB).value
            losses['E_sp'] = los_loss[1].to(cnv.dB).value
            losses['E_sbeta'] = los_loss[2].to(cnv.dB).value

            losses['L_bs'] = trop_loss.to(cnv.dB).value
            losses['L_ba'] = duct_loss.to(cnv.dB).value

            losses['L_d_50'] = diff_loss[0].to(cnv.dB).value
            losses['L_dp'] = diff_loss[1].to(cnv.dB).value
            losses['L_bd_50'] = diff_loss[2].to(cnv.dB).value
            losses['L_bd'] = diff_loss[3].to(cnv.dB).value
            losses['L_min_b0p'] = diff_loss[4].to(cnv.dB).value

            losses['L_bfsg_t'] = tot_loss[0].to(cnv.dB).value
            losses['L_bd_t'] = tot_loss[1].to(cnv.dB).value
            losses['L_bs_t'] = tot_loss[2].to(cnv.dB).value
            losses['L_ba_t'] = tot_loss[3].to(cnv.dB).value
            losses['L_b_t'] = tot_loss[4].to(cnv.dB).value
            losses['L_b_corr_t'] = tot_loss[5].to(cnv.dB).value
            losses['L_t'] = tot_loss[6].to(cnv.dB).value

            # Warning: if uncommenting, the test cases will be overwritten
            # do this only, if you need to update the json files
            # (make sure, that results are correct!)
            # loss_name = self.loss_template.format(
            #     freq, h_tg, h_rg, time_percent, version, G_t, G_r
            #     )
            # json.dump(losses, open(loss_name, 'w'))

    def teardown(self):

        pass

    def test_pathprop(self):

        for freq, (h_tg, h_rg), time_percent, version, _ in self.cases:

            pprop = pathprof.PathProp(
                freq * apu.GHz,
                self.temperature, self.pressure,
                self.lon_t, self.lat_t,
                self.lon_r, self.lat_r,
                h_tg * apu.m, h_rg * apu.m,
                self.hprof_step,
                time_percent * apu.percent,
                version=version,
                )

            pprop_name = self.pprop_template.format(
                freq, h_tg, h_rg, time_percent, version
                )
            pprop_true = json.load(open(pprop_name, 'r'))

            for k in pprop._pp:
                assert_quantity_allclose(pprop._pp[k], pprop_true[k])

    def test_freespace_loss(self):

        for case, pprop in zip(self.cases, self.pprops):

            freq, (h_tg, h_rg), time_percent, version, (G_t, G_r) = case
            los_loss = pathprof.freespace_loss(pprop)
            losses = {}
            losses['L_bfsg'] = los_loss[0].to(cnv.dB).value
            losses['E_sp'] = los_loss[1].to(cnv.dB).value
            losses['E_sbeta'] = los_loss[2].to(cnv.dB).value

            loss_name = self.loss_template.format(
                freq, h_tg, h_rg, time_percent, version, G_t, G_r
                )
            loss_true = json.load(open(loss_name, 'r'))

            for k in losses:
                assert_quantity_allclose(losses[k], loss_true[k])

    def test_troposcatter_loss(self):

        for case, pprop in zip(self.cases, self.pprops):

            freq, (h_tg, h_rg), time_percent, version, (G_t, G_r) = case
            tropo_loss = pathprof.troposcatter_loss(
                pprop, G_t * cnv.dB, G_r * cnv.dB
                )
            losses = {}
            losses['L_bs'] = tropo_loss.to(cnv.dB).value

            loss_name = self.loss_template.format(
                freq, h_tg, h_rg, time_percent, version, G_t, G_r
                )
            loss_true = json.load(open(loss_name, 'r'))

            for k in losses:
                assert_quantity_allclose(losses[k], loss_true[k])

    def test_ducting_loss(self):

        for case, pprop in zip(self.cases, self.pprops):

            freq, (h_tg, h_rg), time_percent, version, (G_t, G_r) = case
            duct_loss = pathprof.ducting_loss(pprop)
            losses = {}
            losses['L_ba'] = duct_loss.to(cnv.dB).value

            loss_name = self.loss_template.format(
                freq, h_tg, h_rg, time_percent, version, G_t, G_r
                )
            loss_true = json.load(open(loss_name, 'r'))

            for k in losses:
                assert_quantity_allclose(losses[k], loss_true[k])

    def test_diffraction_loss(self):

        for case, pprop in zip(self.cases, self.pprops):

            freq, (h_tg, h_rg), time_percent, version, (G_t, G_r) = case
            diff_loss = pathprof.diffraction_loss(pprop)
            losses = {}
            losses['L_d_50'] = diff_loss[0].to(cnv.dB).value
            losses['L_dp'] = diff_loss[1].to(cnv.dB).value
            losses['L_bd_50'] = diff_loss[2].to(cnv.dB).value
            losses['L_bd'] = diff_loss[3].to(cnv.dB).value
            losses['L_min_b0p'] = diff_loss[4].to(cnv.dB).value

            loss_name = self.loss_template.format(
                freq, h_tg, h_rg, time_percent, version, G_t, G_r
                )
            loss_true = json.load(open(loss_name, 'r'))

            for k in losses:
                assert_quantity_allclose(losses[k], loss_true[k])

    def test_complete_loss(self):

        for case, pprop in zip(self.cases, self.pprops):

            freq, (h_tg, h_rg), time_percent, version, (G_t, G_r) = case
            tot_loss = pathprof.complete_loss(
                pprop, G_t * cnv.dB, G_r * cnv.dB
                )
            losses = {}
            losses['L_bfsg_t'] = tot_loss[0].to(cnv.dB).value
            losses['L_bd_t'] = tot_loss[1].to(cnv.dB).value
            losses['L_bs_t'] = tot_loss[2].to(cnv.dB).value
            losses['L_ba_t'] = tot_loss[3].to(cnv.dB).value
            losses['L_b_t'] = tot_loss[4].to(cnv.dB).value
            losses['L_b_corr_t'] = tot_loss[5].to(cnv.dB).value
            losses['L_t'] = tot_loss[6].to(cnv.dB).value

            loss_name = self.loss_template.format(
                freq, h_tg, h_rg, time_percent, version, G_t, G_r
                )
            loss_true = json.load(open(loss_name, 'r'))

            for k in losses:
                assert_quantity_allclose(losses[k], loss_true[k])

    def test_height_profile_data(self, tmpdir_factory):

        hprof_data_cache = pathprof.height_profile_data(
            6.5 * apu.deg, 50.5 * apu.deg,
            900 * apu.arcsec, 900 * apu.arcsec,
            map_resolution=30 * apu.arcsec,
            )

        # also testing reading/writing from hdf5
        tdir = tmpdir_factory.mktemp('hdata')
        tfile = str(tdir.join('hprof.hdf5'))
        print('writing temporary files to', tdir)

        # saving
        with h5py.File(tfile, 'w') as h5f:
            for k, v in hprof_data_cache.items():
                h5f[k] = v

        hprof_data_cache_disk = h5py.File(tfile, 'r')

        for k in hprof_data_cache:
            assert_quantity_allclose(
                # Note conversion to some ndarray type necessary, as h5py
                # returns <HDF5 dataset> types
                np.squeeze(hprof_data_cache[k]),
                np.squeeze(hprof_data_cache_disk[k])
                )

        # also test versus true results
        tfile = os.path.join(this_dir, 'fastmap', 'hprof.hdf5')
        hprof_data_cache_true = h5py.File(tfile, 'r')

        for k in hprof_data_cache:
            assert_quantity_allclose(
                # Note conversion to some ndarray type necessary, as h5py
                # returns <HDF5 dataset> types
                np.squeeze(hprof_data_cache[k]),
                np.squeeze(hprof_data_cache_true[k])
                )

    def test_fast_atten_map(self, tmpdir_factory):

        tfile = os.path.join(this_dir, 'fastmap', 'hprof.hdf5')
        hprof_data_cache = h5py.File(tfile, 'r')

        for case in self.cases:

            freq, (h_tg, h_rg), time_percent, version, (G_t, G_r) = case

            atten_map, eps_pt_map, eps_pr_map = pathprof.atten_map_fast(
                freq * apu.GHz,
                self.temperature,
                self.pressure,
                h_tg * apu.m, h_rg * apu.m,
                time_percent * apu.percent,
                hprof_data_cache,  # dict_like
                version=version,
                )

            atten_map = atten_map.to(cnv.dB).value
            eps_pt_map = eps_pt_map.to(apu.deg).value
            eps_pr_map = eps_pr_map.to(apu.deg).value

            tfile = self.fastmap_template.format(
                freq, h_tg, h_rg, time_percent, version
                )

            # Warning: if uncommenting, the test cases will be overwritten
            # do this only, if you need to update the json files
            # (make sure, that results are correct!)
            # with h5py.File(tfile, 'w') as h5f:
            #     h5f['atten_map'] = atten_map
            #     h5f['eps_pt_map'] = eps_pt_map
            #     h5f['eps_pr_map'] = eps_pr_map

            h5f = h5py.File(tfile, 'r')

            # Note conversion to some ndarray type necessary, as h5py
            # returns <HDF5 dataset> types
            assert_quantity_allclose(h5f['atten_map'], atten_map)
            assert_quantity_allclose(h5f['eps_pt_map'], eps_pt_map)
            assert_quantity_allclose(h5f['eps_pr_map'], eps_pr_map)
