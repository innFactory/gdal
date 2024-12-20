#!/usr/bin/env python3
###############################################################################
#
# Project:  GDAL Python samples
# Purpose:  Script to read coordinate system and geotransformation matrix
#           from input file and report latitude/longitude coordinates for the
#           specified pixel.
# Author:   Andrey Kiselev, dron@remotesensing.org
#
###############################################################################
# Copyright (c) 2003, Andrey Kiselev <dron@remotesensing.org>
# Copyright (c) 2009-2010, Even Rouault <even dot rouault at spatialys.com>
#
# SPDX-License-Identifier: MIT
###############################################################################

import sys

from osgeo import gdal, osr

# =============================================================================


def Usage():
    print("")
    print("Read coordinate system and geotransformation matrix from input")
    print("file and report latitude/longitude coordinates for the center")
    print("of the specified pixel.")
    print("")
    print("Usage: tolatlong.py pixel line infile")
    print("")
    return 2


def main(argv=sys.argv):
    infile = None
    pixel = None
    line = None

    # =============================================================================
    # Parse command line arguments.
    # =============================================================================
    i = 1
    while i < len(argv):
        arg = argv[i]

        if pixel is None:
            pixel = float(arg)

        elif line is None:
            line = float(arg)

        elif infile is None:
            infile = arg

        else:
            return Usage()

        i = i + 1

    if infile is None:
        return Usage()
    if pixel is None:
        return Usage()
    if line is None:
        return Usage()

    # Open input dataset
    indataset = gdal.Open(infile, gdal.GA_ReadOnly)

    # Read geotransform matrix and calculate ground coordinates
    geomatrix = indataset.GetGeoTransform()
    X = geomatrix[0] + geomatrix[1] * pixel + geomatrix[2] * line
    Y = geomatrix[3] + geomatrix[4] * pixel + geomatrix[5] * line

    # Shift to the center of the pixel
    X += geomatrix[1] / 2.0
    Y += geomatrix[5] / 2.0

    # Build Spatial Reference object based on coordinate system, fetched from the
    # opened dataset
    srs = osr.SpatialReference()
    if srs.ImportFromWkt(indataset.GetProjection()) != 0:
        print("ERROR: Cannot import projection '%s'" % indataset.GetProjection())
        return 1

    srsLatLong = srs.CloneGeogCS()
    ct = osr.CoordinateTransformation(srs, srsLatLong)
    (lon, lat, height) = ct.TransformPoint(X, Y)

    # Report results
    print("pixel: %g\t\t\tline: %g" % (pixel, line))
    print("latitude: %fd\t\tlongitude: %fd" % (lat, lon))
    print(
        "latitude: %s\t\tlongitude: %s"
        % (gdal.DecToDMS(lat, "Lat", 2), gdal.DecToDMS(lon, "Long", 2))
    )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
