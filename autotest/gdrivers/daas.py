#!/usr/bin/env python
# -*- coding: utf-8 -*-
###############################################################################
#
# Project:  GDAL/OGR Test Suite
# Purpose:  DAAS driver test suite.
# Author:   Even Rouault, even.rouault at spatialys.com
#
###############################################################################
# Copyright (c) 2018-2019, Airbus DS Intelligence
#
# SPDX-License-Identifier: MIT
###############################################################################

import copy
import json
import sys

sys.path.append("../pymod")

import gdaltest
import pytest
import webserver

from osgeo import gdal

pytestmark = pytest.mark.require_driver("DAAS")


###############################################################################
@pytest.fixture(autouse=True, scope="module")
def module_disable_exceptions():
    with gdaltest.disable_exceptions():
        yield


###############################################################################
@pytest.fixture(autouse=True, scope="module")
def startup_and_cleanup():

    # Unset environment variables that influence the driver behavior
    options = {
        "GDAL_DAAS_API_KEY": None,
        "GDAL_DAAS_CLIENT_ID": None,
        "GDAL_DAAS_AUTH_URL": None,
        "GDAL_DAAS_ACCESS_TOKEN": None,
    }

    (gdaltest.webserver_process, gdaltest.webserver_port) = webserver.launch(
        handler=webserver.DispatcherHttpHandler
    )
    if gdaltest.webserver_port == 0:
        pytest.skip()

    with gdal.config_options(options):
        yield

    if gdaltest.webserver_port != 0:
        webserver.server_stop(gdaltest.webserver_process, gdaltest.webserver_port)

    gdal.RmdirRecursive("/vsimem/cache_dir")


###############################################################################


def test_daas_missing_parameters():

    with gdal.quiet_errors():
        ds = gdal.Open("DAAS:")
        assert not ds


###############################################################################


def test_daas_authentication_failure():

    with gdaltest.config_options(
        {
            "GDAL_DAAS_AUTH_URL": "http://127.0.0.1:%d/auth" % gdaltest.webserver_port,
            "GDAL_DAAS_CLIENT_ID": "client_id",
            "missing_GDAL_DAAS_API_KEY": "api_key",
        }
    ):
        with gdal.quiet_errors():
            ds = gdal.Open("DAAS:https://127.0.0.1:99999")
            assert not ds

    with gdaltest.config_options(
        {
            "GDAL_DAAS_AUTH_URL": "http://127.0.0.1:%d/auth" % gdaltest.webserver_port,
            "missing_GDAL_DAAS_CLIENT_ID": "client_id",
            "GDAL_DAAS_API_KEY": "api_key",
        }
    ):
        with gdal.quiet_errors():
            ds = gdal.Open("DAAS:https://127.0.0.1:99999")
            assert not ds

    handler = webserver.SequentialHandler()
    handler.add(
        "POST",
        "/auth",
        400,
        {},
        '{"error":"unauthorized_client","error_description":"UNKNOWN_CLIENT: Client was not identified by any client authenticator"}',
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_AUTH_URL": "http://127.0.0.1:%d/auth"
                % gdaltest.webserver_port,
                "GDAL_DAAS_CLIENT_ID": "client_id",
                "GDAL_DAAS_API_KEY": "api_key",
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open("DAAS:https://127.0.0.1:99999")
                assert not ds

    handler = webserver.SequentialHandler()
    handler.add("POST", "/auth", 200, {}, "invalid json")
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_AUTH_URL": "http://127.0.0.1:%d/auth"
                % gdaltest.webserver_port,
                "GDAL_DAAS_CLIENT_ID": "client_id",
                "GDAL_DAAS_API_KEY": "api_key",
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open("DAAS:https://127.0.0.1:99999")
                assert not ds

    handler = webserver.SequentialHandler()
    handler.add("POST", "/auth", 200, {}, '{ "missing_access_token": null }')
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_AUTH_URL": "http://127.0.0.1:%d/auth"
                % gdaltest.webserver_port,
                "GDAL_DAAS_CLIENT_ID": "client_id",
                "GDAL_DAAS_API_KEY": "api_key",
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open("DAAS:https://127.0.0.1:99999")
                assert not ds


###############################################################################


def test_daas_authentication():

    # API_KEY + CLIENT_ID
    handler = webserver.SequentialHandler()

    handler.add(
        "POST",
        "/auth",
        200,
        {"Content-type": "application/json"},
        '{"access_token": "my_token"}',
        expected_body="client_id=client_id&apikey=api_key&grant_type=api_key".encode(
            "ascii"
        ),
    )
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        404,
        expected_headers={"Authorization": "Bearer my_token"},
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_AUTH_URL": "http://127.0.0.1:%d/auth"
                % gdaltest.webserver_port,
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
                "GDAL_DAAS_CLIENT_ID": "client_id",
                "GDAL_DAAS_API_KEY": "api_key",
            }
        ):
            with gdal.quiet_errors():
                gdal.Open(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )

    # Test X-Forwarded-User
    handler = webserver.SequentialHandler()
    handler.add("POST", "/auth", 200, {}, '{ "access_token": "my_token" }')
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        404,
        expected_headers={
            "Authorization": "Bearer my_token",
            "X-Forwarded-User": "user",
        },
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_AUTH_URL": "http://127.0.0.1:%d/auth"
                % gdaltest.webserver_port,
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
                "GDAL_DAAS_CLIENT_ID": "client_id",
                "GDAL_DAAS_API_KEY": "api_key",
            }
        ):
            with gdal.quiet_errors():
                gdal.OpenEx(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port,
                    open_options=["X_FORWARDED_USER=user"],
                )

    # Test token expiration
    handler = webserver.SequentialHandler()
    handler.add(
        "POST", "/auth", 200, {}, '{ "access_token": "my_token", "expires_in": 1 }'
    )
    handler.add(
        "POST", "/auth", 200, {}, '{ "access_token": "my_token", "expires_in": 1 }'
    )
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 404, {})
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_AUTH_URL": "http://127.0.0.1:%d/auth"
                % gdaltest.webserver_port,
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
                "GDAL_DAAS_CLIENT_ID": "client_id",
                "GDAL_DAAS_API_KEY": "api_key",
            }
        ):
            with gdal.quiet_errors():
                gdal.Open(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )

    # Test ACCESS_TOKEN
    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        404,
        expected_headers={"Authorization": "Bearer my_token"},
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_ACCESS_TOKEN": "my_token",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                gdal.OpenEx(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )


###############################################################################


def test_daas_getimagemetadata_failure():
    def test_json(j):
        handler = webserver.SequentialHandler()
        handler.add(
            "GET", "/daas/sensors/products/foo/images/bar", 200, {}, json.dumps(j)
        )
        with webserver.install_http_handler(handler):
            with gdaltest.config_options(
                {
                    "GDAL_DAAS_PERFORM_AUTH": "No",
                    "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                    % gdaltest.webserver_port,
                }
            ):
                with gdal.quiet_errors():
                    ds = gdal.Open(
                        "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                        % gdaltest.webserver_port
                    )
                    return ds

    # Empty content returned by server
    handler = webserver.SequentialHandler()
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 404, {})
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )
                assert not ds

    # Error with json payload
    handler = webserver.SequentialHandler()
    handler.add(
        "GET", "/daas/sensors/products/foo/images/bar", 404, {}, '{ "foo":"bar" }'
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )
                assert not ds

    # Success but empty response
    handler = webserver.SequentialHandler()
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 200, {})
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )
                assert not ds

    # Success but invalid JSon
    handler = webserver.SequentialHandler()
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 200, {}, "invalid json")
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )
                assert not ds

    min_valid_json = {
        "properties": {
            "width": 1,
            "height": 1,
            "_links": {"getBuffer": {"href": "http://example.com"}},
            "bands": [{"name": "PAN", "pixelType": "Byte"}],
        }
    }

    # Check that min_valid_json actually works
    gdal.ErrorReset()
    assert test_json(min_valid_json) is not None
    assert gdal.GetLastErrorMsg() == ""

    # Valid JSon but missing response/payload/payload/imageMetadata/properties or properties
    assert test_json({}) is None

    # Valid JSon but missing properties
    for prop_to_del in ["width", "height", "bands", "_links"]:
        j = copy.deepcopy(min_valid_json)
        del j["properties"][prop_to_del]
        assert test_json(j) is None

    # Valid JSon but invalid width (negative value)
    j = copy.deepcopy(min_valid_json)
    j["properties"]["width"] = -1
    assert test_json(j) is None

    # Valid JSon but invalid height (string)
    j = copy.deepcopy(min_valid_json)
    j["properties"]["height"] = "foo"
    assert test_json(j) is None

    # Missing pixelType
    j = copy.deepcopy(min_valid_json)
    del j["properties"]["bands"][0]["pixelType"]
    assert test_json(j) is None

    # Invalid pixelType
    j = copy.deepcopy(min_valid_json)
    j["properties"]["bands"][0]["pixelType"] = "foo"
    assert test_json(j) is None

    # Invalid rpc
    j = copy.deepcopy(min_valid_json)
    j["properties"]["rpc"] = {}
    gdal.ErrorReset()
    ds = test_json(j) is None
    assert gdal.GetLastErrorMsg() != ""


###############################################################################


def test_daas_getimagemetadata():

    # Valid JSon but invalid height (string)
    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 2,
                                    "height": 3,
                                    "actualBitDepth": 7,
                                    "noDataValue": 0,
                                    "metadataInt": 123,
                                    "acquisitionDate": "2018-02-05T22:28:27.242Z",
                                    "cloudCover": 12.345678,
                                    "satellite": "MY_SATELLITE",
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "geotransform": [2, 0, 0.1, 49, 0, -0.1],
                                    "bands": [
                                        {
                                            "name": "PAN",
                                            "description": "Panchromatic band",
                                            "colorInterpretation": "GRAY",
                                            "pixelType": "Byte",
                                        }
                                    ],
                                    "srsExpression": {
                                        "names": [
                                            {"type": "unused", "value": "unused"},
                                            {"type": "proj4", "value": "still_unused"},
                                            {
                                                "type": "urn",
                                                "value": "urn:ogc:def:crs:EPSG::4326",
                                            },
                                            {"type": "proj4", "value": "still_unused"},
                                            {"type": "unused", "value": "unused"},
                                        ]
                                    },
                                    "rpc": {
                                        "sampOff": 1,
                                        "lineOff": 2,
                                        "latOff": 3,
                                        "longOff": 4,
                                        "heightOff": 5,
                                        "lineScale": 6,
                                        "sampScale": 7,
                                        "latScale": 8,
                                        "longScale": 9,
                                        "heightScale": 10,
                                        "lineNumCoeff": [
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                        ],
                                        "lineDenCoeff": [
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                        ],
                                        "sampNumCoeff": [
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                        ],
                                        "sampDenCoeff": [
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                        ],
                                    },
                                }
                            }
                        }
                    }
                }
            }
        ),
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.Open(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port
            )
    assert ds

    assert ds.RasterXSize == 2
    assert ds.RasterYSize == 3
    assert ds.RasterCount == 1
    assert ds.GetGeoTransform() == (2, 0, 0.1, 49, 0, -0.1)
    assert "4326" in ds.GetProjectionRef()

    md = ds.GetMetadata()
    assert md == {
        "metadataInt": "123",
        "satellite": "MY_SATELLITE",
        "cloudCover": "12.345678",
        "acquisitionDate": "2018-02-05T22:28:27.242Z",
    }

    md = ds.GetMetadata("IMAGERY")
    assert md == {
        "ACQUISITIONDATETIME": "2018-02-05 22:28:27",
        "CLOUDCOVER": "12.35",
        "SATELLITEID": "MY_SATELLITE",
    }

    rpc = ds.GetMetadata("RPC")
    expected_rpc = {
        "SAMP_OFF": "1",
        "LINE_OFF": "2",
        "LAT_OFF": "3",
        "LONG_OFF": "4",
        "HEIGHT_OFF": "5",
        "LINE_SCALE": "6",
        "SAMP_SCALE": "7",
        "LAT_SCALE": "8",
        "LONG_SCALE": "9",
        "HEIGHT_SCALE": "10",
        "LINE_NUM_COEFF": "0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9",
        "LINE_DEN_COEFF": "1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0",
        "SAMP_NUM_COEFF": "2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1",
        "SAMP_DEN_COEFF": "3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2",
    }
    assert rpc == expected_rpc
    assert ds.GetRasterBand(1).GetNoDataValue() == 0.0
    assert ds.GetRasterBand(1).GetDescription() == "PAN"
    assert ds.GetRasterBand(1).GetMetadataItem("DESCRIPTION") == "Panchromatic band"
    assert ds.GetRasterBand(1).GetColorInterpretation() == gdal.GCI_GrayIndex
    assert ds.GetRasterBand(1).GetOverviewCount() == 0
    assert ds.GetRasterBand(1).GetOverview(-1) is None
    assert ds.GetRasterBand(1).GetOverview(0) is None

    # Valid JSON with additional RPC error/bias parameters
    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 2,
                                    "height": 3,
                                    "actualBitDepth": 7,
                                    "noDataValue": 0,
                                    "metadataInt": 123,
                                    "acquisitionDate": "2018-02-05T22:28:27.242Z",
                                    "cloudCover": 12.345678,
                                    "satellite": "MY_SATELLITE",
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "geotransform": [2, 0, 0.1, 49, 0, -0.1],
                                    "bands": [
                                        {
                                            "name": "PAN",
                                            "description": "Panchromatic band",
                                            "colorInterpretation": "GRAY",
                                            "pixelType": "Byte",
                                        }
                                    ],
                                    "srsExpression": {
                                        "names": [
                                            {"type": "unused", "value": "unused"},
                                            {"type": "proj4", "value": "still_unused"},
                                            {
                                                "type": "urn",
                                                "value": "urn:ogc:def:crs:EPSG::4326",
                                            },
                                            {"type": "proj4", "value": "still_unused"},
                                            {"type": "unused", "value": "unused"},
                                        ]
                                    },
                                    "rpc": {
                                        "errBias": 1,
                                        "errRand": 2,
                                        "sampOff": 3,
                                        "lineOff": 4,
                                        "latOff": 5,
                                        "longOff": 6,
                                        "heightOff": 7,
                                        "lineScale": 8,
                                        "sampScale": 9,
                                        "latScale": 10,
                                        "longScale": 11,
                                        "heightScale": 12,
                                        "lineNumCoeff": [
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                        ],
                                        "lineDenCoeff": [
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                        ],
                                        "sampNumCoeff": [
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                        ],
                                        "sampDenCoeff": [
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                            3,
                                            4,
                                            5,
                                            6,
                                            7,
                                            8,
                                            9,
                                            0,
                                            1,
                                            2,
                                        ],
                                    },
                                }
                            }
                        }
                    }
                }
            }
        ),
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.Open(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port
            )
    assert ds

    rpc = ds.GetMetadata("RPC")
    expected_rpc = {
        "ERR_BIAS": "1",
        "ERR_RAND": "2",
        "SAMP_OFF": "3",
        "LINE_OFF": "4",
        "LAT_OFF": "5",
        "LONG_OFF": "6",
        "HEIGHT_OFF": "7",
        "LINE_SCALE": "8",
        "SAMP_SCALE": "9",
        "LAT_SCALE": "10",
        "LONG_SCALE": "11",
        "HEIGHT_SCALE": "12",
        "LINE_NUM_COEFF": "0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9",
        "LINE_DEN_COEFF": "1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0",
        "SAMP_NUM_COEFF": "2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1",
        "SAMP_DEN_COEFF": "3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2",
    }
    assert rpc == expected_rpc


###############################################################################


def test_daas_getimagemetadata_http_retry():

    # 4 retries and success
    handler = webserver.SequentialHandler()
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 502, {})
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 503, {})
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 504, {})
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 500, {})
    metadata_response = json.dumps(
        {
            "response": {
                "payload": {
                    "payload": {
                        "imageMetadata": {
                            "properties": {
                                "width": 2,
                                "height": 1,
                                "_links": {
                                    "getBuffer": {
                                        "href": "http://127.0.0.1:%d/getbuffer"
                                        % gdaltest.webserver_port
                                    }
                                },
                                "bands": [
                                    {"name": "Band 1", "pixelType": "Byte"},
                                    {"name": "Band 2", "pixelType": "Byte"},
                                    {"name": "Band 3", "pixelType": "Byte"},
                                ],
                            }
                        }
                    }
                }
            }
        }
    )

    handler.add(
        "GET", "/daas/sensors/products/foo/images/bar", 200, {}, metadata_response
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_INITIAL_RETRY_DELAY": "0.001",
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )
    assert ds

    # 4 retries and failure
    handler = webserver.SequentialHandler()
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 502, {})
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 503, {})
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 504, {})
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 500, {})
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 500, {})
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_INITIAL_RETRY_DELAY": "0.001",
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )
    assert not ds

    # No retry on HTTP 403
    handler = webserver.SequentialHandler()
    handler.add("GET", "/daas/sensors/products/foo/images/bar", 403, {})
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_INITIAL_RETRY_DELAY": "0.001",
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.Open(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port
                )
    assert not ds


###############################################################################


def test_daas_getbuffer_failure():

    metadata_response = json.dumps(
        {
            "response": {
                "payload": {
                    "payload": {
                        "imageMetadata": {
                            "properties": {
                                "width": 2,
                                "height": 1,
                                "_links": {
                                    "getBuffer": {
                                        "href": "http://127.0.0.1:%d/getbuffer"
                                        % gdaltest.webserver_port
                                    }
                                },
                                "bands": [
                                    {"name": "Band 1", "pixelType": "Byte"},
                                    {"name": "Band 2", "pixelType": "Byte"},
                                    {"name": "Band 3", "pixelType": "Byte"},
                                ],
                            }
                        }
                    }
                }
            }
        }
    )

    handler = webserver.SequentialHandler()
    handler.add(
        "GET", "/daas/sensors/products/foo/images/bar", 200, {}, metadata_response
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.OpenEx(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port,
                open_options=["PIXEL_ENCODING=RAW"],
            )
    assert ds

    # HTTP 404
    handler = webserver.SequentialHandler()
    handler.add("POST", "/getbuffer", 404)
    handler.add("POST", "/getbuffer", 404)
    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster()
    assert not data

    # HTTP 404 with payload
    ds.FlushCache()
    handler = webserver.SequentialHandler()
    handler.add("POST", "/getbuffer", 404, {}, "my error message")
    handler.add("POST", "/getbuffer", 404)
    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster()
    assert not data

    # HTTP 200 but invalid multipart
    ds.FlushCache()
    handler = webserver.SequentialHandler()
    handler.add("POST", "/getbuffer", 200, {}, "not multipart")
    handler.add("POST", "/getbuffer", 404)
    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster()
    assert not data

    # Missing data payload part
    ds.FlushCache()
    handler = webserver.SequentialHandler()
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":2,"height":1}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""".replace(
            "\n", "\r\n"
        ),
    )
    handler.add("POST", "/getbuffer", 404)
    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster()
    assert not data

    # Missing metadata part
    ds.FlushCache()
    handler = webserver.SequentialHandler()
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: application/octet-stream

ABCDEF
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""".replace(
            "\n", "\r\n"
        ),
    )
    handler.add("POST", "/getbuffer", 404)
    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster()
    assert not data

    # Inconsistent metadata
    ds.FlushCache()
    handler = webserver.SequentialHandler()
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: application/octet-stream

ABCDEF
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":3,"height":1}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""".replace(
            "\n", "\r\n"
        ),
    )
    handler.add("POST", "/getbuffer", 404)
    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster()
    assert not data

    # Inconsistent data size
    ds.FlushCache()
    handler = webserver.SequentialHandler()
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: application/octet-stream

ABCDE
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":2,"height":1}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""".replace(
            "\n", "\r\n"
        ),
    )
    handler.add("POST", "/getbuffer", 404)
    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster()
    assert not data

    # Invalid PNG image
    ds.FlushCache()
    handler = webserver.SequentialHandler()
    handler.add(
        "GET", "/daas/sensors/products/foo/images/bar", 200, {}, metadata_response
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.OpenEx(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port
            )
    assert ds

    handler = webserver.SequentialHandler()
    png_content = "This is not png !".encode("ascii")
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: image/png

""".replace(
            "\n", "\r\n"
        ).encode(
            "ascii"
        )
        + png_content
        + """
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":2,"height":1}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""".replace(
            "\n", "\r\n"
        ).encode(
            "ascii"
        ),
    )
    handler.add("POST", "/getbuffer", 404)

    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster()
    assert not data

    # Inconsistent PNG image
    ds.FlushCache()
    handler = webserver.SequentialHandler()
    png_content = open("data/png/test.png", "rb").read()
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: image/png

""".replace(
            "\n", "\r\n"
        ).encode(
            "ascii"
        )
        + png_content
        + """
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":2,"height":1}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""".replace(
            "\n", "\r\n"
        ).encode(
            "ascii"
        ),
    )
    handler.add("POST", "/getbuffer", 404)

    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster()
    assert not data


###############################################################################


def test_daas_getbuffer_pixel_encoding_failures():

    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 2,
                                    "height": 1,
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "bands": [
                                        {"name": "Band 1", "pixelType": "UInt16"}
                                    ],
                                }
                            }
                        }
                    }
                }
            }
        ),
    )

    # PNG with UInt16 -> unsupported
    gdal.ErrorReset()
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.OpenEx(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port,
                    open_options=["PIXEL_ENCODING=PNG"],
                )
    assert ds
    assert gdal.GetLastErrorMsg() != ""

    # JPEG with UInt16 -> unsupported
    gdal.ErrorReset()
    handler.req_count = 0
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.OpenEx(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port,
                    open_options=["PIXEL_ENCODING=JPEG"],
                )
    assert ds
    assert gdal.GetLastErrorMsg() != ""

    # PIXEL_ENCODING=FOO -> unsupported
    gdal.ErrorReset()
    handler.req_count = 0
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.OpenEx(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port,
                    open_options=["PIXEL_ENCODING=FOO"],
                )
    assert not ds

    # JPEG2000 with Float32 -> unsupported
    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 2,
                                    "height": 1,
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "bands": [
                                        {
                                            "name": "Band 1",
                                            "pixelType": "Float32",
                                        }
                                    ],
                                }
                            }
                        }
                    }
                }
            }
        ),
    )

    gdal.ErrorReset()
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            with gdal.quiet_errors():
                ds = gdal.OpenEx(
                    "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                    % gdaltest.webserver_port,
                    open_options=["PIXEL_ENCODING=JPEG2000"],
                )
    assert ds
    assert gdal.GetLastErrorMsg() != ""


###############################################################################


def test_daas_getbuffer_raw():

    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 2,
                                    "height": 1,
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "bands": [
                                        {"name": "Band 1", "pixelType": "Byte"},
                                        {"name": "Band 2", "pixelType": "Byte"},
                                        {"name": "Band 3", "pixelType": "Byte"},
                                    ],
                                }
                            }
                        }
                    }
                }
            }
        ),
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.OpenEx(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port,
                open_options=["PIXEL_ENCODING=RAW"],
            )
    assert ds

    handler = webserver.SequentialHandler()
    response = """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: application/octet-stream

ABCDEF
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":2,"height":1}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--"""
    response = response.replace("\n", "\r\n")
    expected_body = """{
  "bbox":{
    "srs":{
      "type":"image"
    },
    "ul":{
      "x":0,
      "y":0
    },
    "lr":{
      "x":2,
      "y":1
    }
  },
  "target-model":{
    "step":{
      "x":0,
      "y":0
    },
    "size":{
      "columns":2,
      "lines":1
    },
    "sampling-algo":"NEAREST",
    "strictOutputSize":true,
    "srs":{
      "type":"image"
    }
  },
  "bands":[
    "Band 1",
    "Band 2",
    "Band 3"
  ]
}""".encode(
        "ascii"
    )
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response,
        expected_headers={"Accept": "application/octet-stream"},
        expected_body=expected_body,
    )
    with webserver.install_http_handler(handler):
        data = ds.GetRasterBand(1).ReadRaster()
    assert data == "AB".encode("ascii")


###############################################################################


@pytest.mark.parametrize(
    "pixel_encoding,drv_name,drv_options,mime_type",
    [
        (
            "JPEG2000",
            "JP2OPENJPEG",
            ["QUALITY=100", "REVERSIBLE=YES", "RESOLUTIONS=1", "CODEC=JP2"],
            "image/jp2",
        ),
        ("JPEG2000", "JP2KAK", ["QUALITY=100", "CODEC=JP2"], "image/jp2"),
        ("JPEG", "JPEG", ["QUALITY=100"], "image/jpeg"),
        ("PNG", "PNG", [], "image/png"),
    ],
    ids=("jpeg2000_jp2openjpeg", "jpeg2000_jp2kak", "jpeg", "png"),
)
def test_daas_getbuffer(tmp_vsimem, pixel_encoding, drv_name, drv_options, mime_type):

    drv = gdal.GetDriverByName(drv_name)
    if drv is None:
        pytest.skip(f"Driver {drv_name} not available")

    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 100,
                                    "height": 100,
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "bands": [
                                        {"name": "Band 1", "pixelType": "Byte"},
                                        {"name": "Band 2", "pixelType": "Byte"},
                                        {"name": "Band 3", "pixelType": "Byte"},
                                    ],
                                }
                            }
                        }
                    }
                }
            }
        ),
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.OpenEx(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port,
                open_options=["PIXEL_ENCODING=" + pixel_encoding],
            )
    assert ds

    handler = webserver.SequentialHandler()
    src_ds = gdal.GetDriverByName("MEM").Create("", 100, 100, 3)
    src_ds.GetRasterBand(1).WriteRaster(0, 0, 100, 100, "A", buf_xsize=1, buf_ysize=1)
    src_ds.GetRasterBand(2).WriteRaster(0, 0, 100, 100, "B", buf_xsize=1, buf_ysize=1)
    src_ds.GetRasterBand(3).WriteRaster(0, 0, 100, 100, "C", buf_xsize=1, buf_ysize=1)
    tmpfile = tmp_vsimem / "tmp"
    drv.CreateCopy(tmpfile, src_ds, options=drv_options)
    f = gdal.VSIFOpenL(tmpfile, "rb")
    content = gdal.VSIFReadL(1, 10000, f)
    gdal.VSIFCloseL(f)
    gdal.Unlink(tmpfile)

    response = (
        (
            """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: """
            + mime_type
            + """

"""
        )
        .replace("\n", "\r\n")
        .encode("ascii")
        + content
        + """
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":100,"height":100}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""".replace(
            "\n", "\r\n"
        ).encode(
            "ascii"
        )
    )
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response,
        expected_headers={"Accept": mime_type},
    )

    with webserver.install_http_handler(handler):
        with gdal.quiet_errors():
            data = ds.GetRasterBand(1).ReadRaster(0, 0, 1, 1)
    assert data == "A".encode("ascii")
    data = ds.GetRasterBand(2).ReadRaster(0, 0, 1, 1)
    assert data == "B".encode("ascii")


###############################################################################


def test_daas_getbuffer_overview():

    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 1024,
                                    "height": 512,
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "bands": [{"name": "Band 1", "pixelType": "Byte"}],
                                }
                            }
                        }
                    }
                }
            }
        ),
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.OpenEx(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port,
                open_options=["PIXEL_ENCODING=RAW"],
            )
    assert ds

    assert ds.GetRasterBand(1).GetOverviewCount() == 2
    ovr0 = ds.GetRasterBand(1).GetOverview(0)
    assert ovr0.XSize == 512
    assert ovr0.YSize == 256

    handler = webserver.SequentialHandler()
    response = """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: application/octet-stream

%s
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":512,"height":256}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""" % (
        " " * (512 * 256)
    )
    response = response.replace("\n", "\r\n")

    expected_body = """{
  "bbox":{
    "srs":{
      "type":"image"
    },
    "ul":{
      "x":0,
      "y":0
    },
    "lr":{
      "x":1024,
      "y":512
    }
  },
  "target-model":{
    "step":{
      "x":0,
      "y":0
    },
    "size":{
      "columns":512,
      "lines":256
    },
    "sampling-algo":"NEAREST",
    "strictOutputSize":true,
    "srs":{
      "type":"image"
    }
  },
  "bands":[
    "Band 1"
  ]
}""".encode(
        "ascii"
    )
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response,
        expected_body=expected_body,
    )

    with webserver.install_http_handler(handler):
        data = ds.GetRasterBand(1).ReadRaster(0, 0, 1024, 512, 512, 256)
    assert data


###############################################################################


def test_daas_rasterio():

    handler_metadata = webserver.SequentialHandler()
    handler_metadata.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 1024,
                                    "height": 512,
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "bands": [
                                        {"name": "Band 1", "pixelType": "UInt16"}
                                    ],
                                }
                            }
                        }
                    }
                }
            }
        ),
    )
    with webserver.install_http_handler(handler_metadata):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.OpenEx(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port,
                open_options=["PIXEL_ENCODING=RAW"],
            )
    assert ds

    handler = webserver.SequentialHandler()
    response = """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: application/octet-stream

%s
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":1024,"height":512}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""" % (
        " " * (1024 * 512 * 2)
    )
    response = response.replace("\n", "\r\n")

    expected_body = """{
  "bbox":{
    "srs":{
      "type":"image"
    },
    "ul":{
      "x":0,
      "y":0
    },
    "lr":{
      "x":1024,
      "y":512
    }
  },
  "target-model":{
    "step":{
      "x":0,
      "y":0
    },
    "size":{
      "columns":1024,
      "lines":512
    },
    "sampling-algo":"NEAREST",
    "strictOutputSize":true,
    "srs":{
      "type":"image"
    }
  },
  "bands":[
    "Band 1"
  ]
}""".encode(
        "ascii"
    )
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response,
        expected_body=expected_body,
    )

    # Check that AdviseRead is properly honoured
    ds.AdviseRead(0, 0, 1024, 512)
    with webserver.install_http_handler(handler):
        data = ds.ReadRaster(0, 0, 512, 512)
    assert data
    data = ds.ReadRaster(0, 0, 512, 512)
    assert data
    data = ds.ReadRaster(512, 0, 512, 512)
    assert data

    # Redo at band level
    ds.FlushCache()
    ds.GetRasterBand(1).AdviseRead(0, 0, 1024, 512)
    handler.req_count = 0
    with webserver.install_http_handler(handler):
        data = ds.GetRasterBand(1).ReadRaster(0, 0, 512, 512)
    assert data

    # Re-test by simulating hitting server byte limit
    handler_metadata.req_count = 0
    with webserver.install_http_handler(handler_metadata):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_SERVER_BYTE_LIMIT": "%d" % (512 * 512),
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.OpenEx(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port,
                open_options=["PIXEL_ENCODING=RAW"],
            )
    assert ds

    ds.GetRasterBand(1).AdviseRead(0, 0, 1024, 512)

    handler = webserver.SequentialHandler()
    response = """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: application/octet-stream

%s
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":512,"height":512}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""" % (
        " " * (512 * 512 * 2)
    )
    response = response.replace("\n", "\r\n")

    expected_body = """{
  "bbox":{
    "srs":{
      "type":"image"
    },
    "ul":{
      "x":0,
      "y":0
    },
    "lr":{
      "x":512,
      "y":512
    }
  },
  "target-model":{
    "step":{
      "x":0,
      "y":0
    },
    "size":{
      "columns":512,
      "lines":512
    },
    "sampling-algo":"NEAREST",
    "strictOutputSize":true,
    "srs":{
      "type":"image"
    }
  },
  "bands":[
    "Band 1"
  ]
}""".encode(
        "ascii"
    )
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response,
        expected_body=expected_body,
    )
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response,
    )
    with webserver.install_http_handler(handler):
        data = ds.GetRasterBand(1).ReadRaster(0, 0, 1024, 512)
    assert data


###############################################################################


def test_daas_mask():

    # Valid JSon but invalid height (string)
    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 2,
                                    "height": 3,
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "geotransform": [2, 0, 0.1, 49, 0, -0.1],
                                    "bands": [
                                        {
                                            "name": "PAN",
                                            "description": "Panchromatic band",
                                            "colorInterpretation": "GRAY",
                                            "pixelType": "UInt16",
                                        },
                                        {
                                            "name": "THE_MASK",
                                            "colorInterpretation": "MAIN_MASK",
                                            "pixelType": "Byte",
                                        },
                                    ],
                                }
                            }
                        }
                    }
                }
            }
        ),
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.OpenEx(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port,
                open_options=["PIXEL_ENCODING=RAW"],
            )
    assert ds.RasterCount == 1
    assert ds.GetRasterBand(1).GetMaskFlags() == gdal.GMF_PER_DATASET
    assert ds.GetRasterBand(1).GetMaskBand()
    assert ds.GetRasterBand(1).GetNoDataValue() is None

    # Test a non-typical answer where the server returns a pixelType=Band for the PAN band
    # instead of UInt16
    response = """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: application/octet-stream

%s
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":2,"height":3,"bands":[{"name":"PAN","pixelType":"Byte"}]}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""" % (
        "XXXXXX"
    )
    response = response.replace("\n", "\r\n")

    response2 = """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: application/octet-stream

%s
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":2,"height":3,"bands":[{"name":"THE_MASK","pixelType":"Byte"}]}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""" % (
        "GHIJKL"
    )
    response2 = response2.replace("\n", "\r\n")

    handler = webserver.SequentialHandler()
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response,
    )
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response2,
    )

    with webserver.install_http_handler(handler):
        data = ds.GetRasterBand(1).GetMaskBand().ReadRaster(buf_type=gdal.GDT_Byte)
    assert data == "GHIJKL".encode("ascii")

    ds.FlushCache()

    handler = webserver.SequentialHandler()
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response,
    )
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        response2,
    )
    with webserver.install_http_handler(handler):
        data = ds.ReadRaster(buf_type=gdal.GDT_Byte)
    assert data == "XXXXXX".encode("ascii")
    data = ds.GetRasterBand(1).GetMaskBand().ReadRaster(buf_type=gdal.GDT_Byte)
    assert data == "GHIJKL".encode("ascii")


###############################################################################


def test_daas_png_response_4_bands_for_a_one_band_request(tmp_vsimem):

    # Valid JSon but invalid height (string)
    handler = webserver.SequentialHandler()
    handler.add(
        "GET",
        "/daas/sensors/products/foo/images/bar",
        200,
        {},
        json.dumps(
            {
                "response": {
                    "payload": {
                        "payload": {
                            "imageMetadata": {
                                "properties": {
                                    "width": 2,
                                    "height": 3,
                                    "_links": {
                                        "getBuffer": {
                                            "href": "http://127.0.0.1:%d/getbuffer"
                                            % gdaltest.webserver_port
                                        }
                                    },
                                    "bands": [
                                        {
                                            "name": "PAN",
                                            "description": "Panchromatic band",
                                            "colorInterpretation": "GRAY",
                                            "pixelType": "Byte",
                                        }
                                    ],
                                }
                            }
                        }
                    }
                }
            }
        ),
    )
    with webserver.install_http_handler(handler):
        with gdaltest.config_options(
            {
                "GDAL_DAAS_PERFORM_AUTH": "No",
                "GDAL_DAAS_SERVICE_URL": "http://127.0.0.1:%d/daas"
                % gdaltest.webserver_port,
            }
        ):
            ds = gdal.OpenEx(
                "DAAS:http://127.0.0.1:%d/daas/sensors/products/foo/images/bar"
                % gdaltest.webserver_port
            )
    assert ds.RasterCount == 1

    src_ds = gdal.GetDriverByName("MEM").Create("", 2, 3, 4)
    src_ds.GetRasterBand(1).WriteRaster(0, 0, 2, 3, "A", buf_xsize=1, buf_ysize=1)
    src_ds.GetRasterBand(2).WriteRaster(0, 0, 2, 3, "B", buf_xsize=1, buf_ysize=1)
    src_ds.GetRasterBand(3).WriteRaster(0, 0, 2, 3, "C", buf_xsize=1, buf_ysize=1)
    src_ds.GetRasterBand(4).WriteRaster(0, 0, 2, 3, "D", buf_xsize=1, buf_ysize=1)
    tmpfile = tmp_vsimem / "out.png"
    gdal.GetDriverByName("PNG").CreateCopy(tmpfile, src_ds)
    f = gdal.VSIFOpenL(tmpfile, "rb")
    png_content = gdal.VSIFReadL(1, 10000, f)
    gdal.VSIFCloseL(f)
    gdal.Unlink(tmpfile)

    handler = webserver.SequentialHandler()
    handler.add(
        "POST",
        "/getbuffer",
        200,
        {
            "Content-Type": "multipart/form-data; boundary=bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7"
        },
        """--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Data";
Content-Type: image/png

""".replace(
            "\n", "\r\n"
        ).encode(
            "ascii"
        )
        + png_content
        + """
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7
Content-Disposition: form-data; name="Info";
Content-Type: application/json

{"properties":{"format":"application/octet-stream","width":2,"height":3}}
--bd3f250361b619a49ef290d4fdfcf5d5691e385e5a74254803befd5fe2a7--""".replace(
            "\n", "\r\n"
        ).encode(
            "ascii"
        ),
    )

    with webserver.install_http_handler(handler):
        data = ds.GetRasterBand(1).ReadRaster()
    assert data == "AAAAAA".encode("ascii")
