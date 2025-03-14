/**********************************************************************
 *
 * Name:     mitab_ogr_datasource.cpp
 * Project:  MapInfo Mid/Mif, Tab ogr support
 * Language: C++
 * Purpose:  Implementation of OGRTABDataSource.
 * Author:   Stephane Villeneuve, stephane.v@videotron.ca
 *           and Frank Warmerdam, warmerdam@pobox.com
 *
 **********************************************************************
 * Copyright (c) 1999, 2000, Stephane Villeneuve
 * Copyright (c) 2014, Even Rouault <even.rouault at spatialys.com>
 *
 * SPDX-License-Identifier: MIT
 **********************************************************************/

#include "mitab_ogr_driver.h"

/*=======================================================================
 *                 OGRTABDataSource
 *
 * We need one single OGRDataSource/Driver set of classes to handle all
 * the MapInfo file types.  They all deal with the IMapInfoFile abstract
 * class.
 *=====================================================================*/

/************************************************************************/
/*                         OGRTABDataSource()                           */
/************************************************************************/

OGRTABDataSource::OGRTABDataSource()
    : m_pszDirectory(nullptr), m_nLayerCount(0), m_papoLayers(nullptr),
      m_papszOptions(nullptr), m_bCreateMIF(FALSE), m_bSingleFile(FALSE),
      m_bSingleLayerAlreadyCreated(FALSE), m_bQuickSpatialIndexMode(-1),
      m_nBlockSize(512)
{
}

/************************************************************************/
/*                         ~OGRTABDataSource()                          */
/************************************************************************/

OGRTABDataSource::~OGRTABDataSource()

{
    CPLFree(m_pszDirectory);

    for (int i = 0; i < m_nLayerCount; i++)
        delete m_papoLayers[i];

    CPLFree(m_papoLayers);
    CSLDestroy(m_papszOptions);
}

/************************************************************************/
/*                               Create()                               */
/*                                                                      */
/*      Create a new dataset (directory or file).                       */
/************************************************************************/

int OGRTABDataSource::Create(const char *pszName, char **papszOptions)

{
    SetDescription(pszName);
    m_papszOptions = CSLDuplicate(papszOptions);
    eAccess = GA_Update;

    const char *pszOpt = CSLFetchNameValue(papszOptions, "FORMAT");
    if (pszOpt != nullptr && EQUAL(pszOpt, "MIF"))
        m_bCreateMIF = TRUE;
    else if (EQUAL(CPLGetExtensionSafe(pszName).c_str(), "mif") ||
             EQUAL(CPLGetExtensionSafe(pszName).c_str(), "mid"))
        m_bCreateMIF = TRUE;

    if ((pszOpt = CSLFetchNameValue(papszOptions, "SPATIAL_INDEX_MODE")) !=
        nullptr)
    {
        if (EQUAL(pszOpt, "QUICK"))
            m_bQuickSpatialIndexMode = TRUE;
        else if (EQUAL(pszOpt, "OPTIMIZED"))
            m_bQuickSpatialIndexMode = FALSE;
    }

    m_nBlockSize = atoi(CSLFetchNameValueDef(papszOptions, "BLOCKSIZE", "512"));

    // Create a new empty directory.
    VSIStatBufL sStat;

    if (strlen(CPLGetExtensionSafe(pszName).c_str()) == 0)
    {
        if (VSIStatL(pszName, &sStat) == 0)
        {
            if (!VSI_ISDIR(sStat.st_mode))
            {
                CPLError(CE_Failure, CPLE_OpenFailed,
                         "Attempt to create dataset named %s,\n"
                         "but that is an existing file.",
                         pszName);
                return FALSE;
            }
        }
        else
        {
            if (VSIMkdir(pszName, 0755) != 0)
            {
                CPLError(CE_Failure, CPLE_AppDefined,
                         "Unable to create directory %s.", pszName);
                return FALSE;
            }
        }

        m_pszDirectory = CPLStrdup(pszName);
    }

    // Create a new single file.
    else
    {
        IMapInfoFile *poFile = nullptr;
        const char *pszEncoding(CSLFetchNameValue(papszOptions, "ENCODING"));
        const char *pszCharset(IMapInfoFile::EncodingToCharset(pszEncoding));
        bool bStrictLaundering = CPLTestBool(CSLFetchNameValueDef(
            papszOptions, "STRICT_FIELDS_NAME_LAUNDERING", "YES"));
        if (m_bCreateMIF)
        {
            poFile = new MIFFile(this);
            if (poFile->Open(pszName, TABWrite, FALSE, pszCharset) != 0)
            {
                delete poFile;
                return FALSE;
            }
        }
        else
        {
            TABFile *poTabFile = new TABFile(this);
            if (poTabFile->Open(pszName, TABWrite, FALSE, m_nBlockSize,
                                pszCharset) != 0)
            {
                delete poTabFile;
                return FALSE;
            }
            poFile = poTabFile;
        }
        poFile->SetStrictLaundering(bStrictLaundering);
        m_nLayerCount = 1;
        m_papoLayers = static_cast<IMapInfoFile **>(CPLMalloc(sizeof(void *)));
        m_papoLayers[0] = poFile;

        m_pszDirectory = CPLStrdup(CPLGetPathSafe(pszName).c_str());
        m_bSingleFile = TRUE;
    }

    return TRUE;
}

/************************************************************************/
/*                                Open()                                */
/*                                                                      */
/*      Open an existing file, or directory of files.                   */
/************************************************************************/

int OGRTABDataSource::Open(GDALOpenInfo *poOpenInfo, int bTestOpen)

{
    SetDescription(poOpenInfo->pszFilename);
    eAccess = poOpenInfo->eAccess;

    // If it is a file, try to open as a Mapinfo file.
    if (!poOpenInfo->bIsDirectory)
    {
        IMapInfoFile *poFile = IMapInfoFile::SmartOpen(
            this, poOpenInfo->pszFilename, GetUpdate(), bTestOpen);
        if (poFile == nullptr)
            return FALSE;

        poFile->SetDescription(poFile->GetName());

        m_nLayerCount = 1;
        m_papoLayers = static_cast<IMapInfoFile **>(CPLMalloc(sizeof(void *)));
        m_papoLayers[0] = poFile;

        m_pszDirectory =
            CPLStrdup(CPLGetPathSafe(poOpenInfo->pszFilename).c_str());

        m_bSingleFile = TRUE;
        m_bSingleLayerAlreadyCreated = TRUE;
    }

    // Otherwise, we need to scan the whole directory for files
    // ending in .tab or .mif.
    else
    {
        char **papszFileList = VSIReadDir(poOpenInfo->pszFilename);

        m_pszDirectory = CPLStrdup(poOpenInfo->pszFilename);

        for (int iFile = 0;
             papszFileList != nullptr && papszFileList[iFile] != nullptr;
             iFile++)
        {
            const std::string osExtension =
                CPLGetExtensionSafe(papszFileList[iFile]);

            if (!EQUAL(osExtension.c_str(), "tab") &&
                !EQUAL(osExtension.c_str(), "mif"))
                continue;

            char *pszSubFilename =
                CPLStrdup(CPLFormFilenameSafe(m_pszDirectory,
                                              papszFileList[iFile], nullptr)
                              .c_str());

            IMapInfoFile *poFile = IMapInfoFile::SmartOpen(
                this, pszSubFilename, GetUpdate(), bTestOpen);
            CPLFree(pszSubFilename);

            if (poFile == nullptr)
            {
                CSLDestroy(papszFileList);
                return FALSE;
            }
            poFile->SetDescription(poFile->GetName());

            m_nLayerCount++;
            m_papoLayers = static_cast<IMapInfoFile **>(
                CPLRealloc(m_papoLayers, sizeof(void *) * m_nLayerCount));
            m_papoLayers[m_nLayerCount - 1] = poFile;
        }

        CSLDestroy(papszFileList);

        if (m_nLayerCount == 0)
        {
            if (!bTestOpen)
                CPLError(CE_Failure, CPLE_OpenFailed,
                         "No mapinfo files found in directory %s.",
                         m_pszDirectory);

            return FALSE;
        }
    }

    return TRUE;
}

/************************************************************************/
/*                           GetLayerCount()                            */
/************************************************************************/

int OGRTABDataSource::GetLayerCount()

{
    if (m_bSingleFile && !m_bSingleLayerAlreadyCreated)
        return 0;
    else
        return m_nLayerCount;
}

/************************************************************************/
/*                              GetLayer()                              */
/************************************************************************/

OGRLayer *OGRTABDataSource::GetLayer(int iLayer)

{
    if (iLayer < 0 || iLayer >= GetLayerCount())
        return nullptr;
    else
        return m_papoLayers[iLayer];
}

/************************************************************************/
/*                           ICreateLayer()                             */
/************************************************************************/

OGRLayer *
OGRTABDataSource::ICreateLayer(const char *pszLayerName,
                               const OGRGeomFieldDefn *poGeomFieldDefnIn,
                               CSLConstList papszOptions)

{
    if (!GetUpdate())
    {
        CPLError(CE_Failure, CPLE_AppDefined,
                 "Cannot create layer on read-only dataset.");
        return nullptr;
    }

    const auto poSRSIn =
        poGeomFieldDefnIn ? poGeomFieldDefnIn->GetSpatialRef() : nullptr;

    // If it is a single file mode file, then we may have already
    // instantiated the low level layer.   We would just need to
    // reset the coordinate system and (potentially) bounds.
    IMapInfoFile *poFile = nullptr;
    char *pszFullFilename = nullptr;

    const char *pszEncoding = CSLFetchNameValue(papszOptions, "ENCODING");
    const char *pszCharset(IMapInfoFile::EncodingToCharset(pszEncoding));
    const char *pszDescription(CSLFetchNameValue(papszOptions, "DESCRIPTION"));
    const char *pszStrictLaundering =
        CSLFetchNameValue(papszOptions, "STRICT_FIELDS_NAME_LAUNDERING");
    if (pszStrictLaundering == nullptr)
    {
        pszStrictLaundering = CSLFetchNameValueDef(
            m_papszOptions, "STRICT_FIELDS_NAME_LAUNDERING", "YES");
    }
    bool bStrictLaundering = CPLTestBool(pszStrictLaundering);

    if (m_bSingleFile)
    {
        if (m_bSingleLayerAlreadyCreated)
        {
            CPLError(
                CE_Failure, CPLE_AppDefined,
                "Unable to create new layers in this single file dataset.");
            return nullptr;
        }

        m_bSingleLayerAlreadyCreated = TRUE;

        poFile = m_papoLayers[0];
        if (pszEncoding)
            poFile->SetCharset(pszCharset);

        if (poFile->GetFileClass() == TABFC_TABFile)
            poFile->SetMetadataItem("DESCRIPTION", pszDescription);
    }

    else
    {
        if (m_bCreateMIF)
        {
            pszFullFilename = CPLStrdup(
                CPLFormFilenameSafe(m_pszDirectory, pszLayerName, "mif")
                    .c_str());

            poFile = new MIFFile(this);

            if (poFile->Open(pszFullFilename, TABWrite, FALSE, pszCharset) != 0)
            {
                CPLFree(pszFullFilename);
                delete poFile;
                return nullptr;
            }
        }
        else
        {
            pszFullFilename = CPLStrdup(
                CPLFormFilenameSafe(m_pszDirectory, pszLayerName, "tab")
                    .c_str());

            TABFile *poTABFile = new TABFile(this);

            if (poTABFile->Open(pszFullFilename, TABWrite, FALSE, m_nBlockSize,
                                pszCharset) != 0)
            {
                CPLFree(pszFullFilename);
                delete poTABFile;
                return nullptr;
            }
            poFile = poTABFile;
            poFile->SetMetadataItem("DESCRIPTION", pszDescription);
        }

        m_nLayerCount++;
        m_papoLayers = static_cast<IMapInfoFile **>(
            CPLRealloc(m_papoLayers, sizeof(void *) * m_nLayerCount));
        m_papoLayers[m_nLayerCount - 1] = poFile;

        CPLFree(pszFullFilename);
    }

    poFile->SetDescription(poFile->GetName());
    poFile->SetStrictLaundering(bStrictLaundering);

    // Assign the coordinate system (if provided) and set
    // reasonable bounds.
    if (poSRSIn != nullptr)
    {
        auto poSRSClone = poSRSIn->Clone();
        poSRSClone->SetAxisMappingStrategy(OAMS_TRADITIONAL_GIS_ORDER);
        poFile->SetSpatialRef(poSRSClone);
        poSRSClone->Release();
        // SetSpatialRef() has cloned the passed geometry
        auto poGeomFieldDefn = poFile->GetLayerDefn()->GetGeomFieldDefn(0);
        auto oTemporaryUnsealer(poGeomFieldDefn->GetTemporaryUnsealer());
        poGeomFieldDefn->SetSpatialRef(poFile->GetSpatialRef());
    }

    // Pull out the bounds if supplied
    const char *pszOpt = nullptr;
    if ((pszOpt = CSLFetchNameValue(papszOptions, "BOUNDS")) != nullptr)
    {
        double dfBounds[4];
        if (CPLsscanf(pszOpt, "%lf,%lf,%lf,%lf", &dfBounds[0], &dfBounds[1],
                      &dfBounds[2], &dfBounds[3]) != 4)
        {
            CPLError(
                CE_Failure, CPLE_IllegalArg,
                "Invalid BOUNDS parameter, expected min_x,min_y,max_x,max_y");
        }
        else
        {
            poFile->SetBounds(dfBounds[0], dfBounds[1], dfBounds[2],
                              dfBounds[3]);
        }
    }

    if (!poFile->IsBoundsSet() && !m_bCreateMIF)
    {
        if (poSRSIn != nullptr && poSRSIn->IsGeographic())
            poFile->SetBounds(-1000, -1000, 1000, 1000);
        else if (poSRSIn != nullptr && poSRSIn->IsProjected())
        {
            const double FE = poSRSIn->GetProjParm(SRS_PP_FALSE_EASTING, 0.0);
            const double FN = poSRSIn->GetProjParm(SRS_PP_FALSE_NORTHING, 0.0);
            poFile->SetBounds(-30000000 + FE, -15000000 + FN, 30000000 + FE,
                              15000000 + FN);
        }
        else
            poFile->SetBounds(-30000000, -15000000, 30000000, 15000000);
    }

    if (m_bQuickSpatialIndexMode == TRUE &&
        poFile->SetQuickSpatialIndexMode(TRUE) != 0)
    {
        CPLError(CE_Warning, CPLE_AppDefined,
                 "Setting Quick Spatial Index Mode failed.");
    }
    else if (m_bQuickSpatialIndexMode == FALSE &&
             poFile->SetQuickSpatialIndexMode(FALSE) != 0)
    {
        CPLError(CE_Warning, CPLE_AppDefined,
                 "Setting Normal Spatial Index Mode failed.");
    }

    return poFile;
}

/************************************************************************/
/*                           TestCapability()                           */
/************************************************************************/

int OGRTABDataSource::TestCapability(const char *pszCap)

{
    if (EQUAL(pszCap, ODsCCreateLayer))
        return GetUpdate() && (!m_bSingleFile || !m_bSingleLayerAlreadyCreated);
    else if (EQUAL(pszCap, ODsCRandomLayerWrite))
        return GetUpdate();
    else
        return FALSE;
}

/************************************************************************/
/*                            GetFileList()                             */
/************************************************************************/

char **OGRTABDataSource::GetFileList()
{
    VSIStatBufL sStatBuf;
    CPLStringList osList;

    if (VSIStatL(GetDescription(), &sStatBuf) == 0 &&
        VSI_ISDIR(sStatBuf.st_mode))
    {
        static const char *const apszExtensions[] = {
            "mif", "mid", "tab", "map", "ind", "dat", "id", nullptr};
        char **papszDirEntries = VSIReadDir(GetDescription());

        for (int iFile = 0;
             papszDirEntries != nullptr && papszDirEntries[iFile] != nullptr;
             iFile++)
        {
            if (CSLFindString(
                    apszExtensions,
                    CPLGetExtensionSafe(papszDirEntries[iFile]).c_str()) != -1)
            {
                osList.push_back(CPLFormFilenameSafe(
                    GetDescription(), papszDirEntries[iFile], nullptr));
            }
        }

        CSLDestroy(papszDirEntries);
    }
    else
    {
        static const char *const apszMIFExtensions[] = {"mif", "mid", nullptr};
        static const char *const apszTABExtensions[] = {"tab", "map", "ind",
                                                        "dat", "id",  nullptr};
        const char *const *papszExtensions = nullptr;
        if (EQUAL(CPLGetExtensionSafe(GetDescription()).c_str(), "mif") ||
            EQUAL(CPLGetExtensionSafe(GetDescription()).c_str(), "mid"))
        {
            papszExtensions = apszMIFExtensions;
        }
        else
        {
            papszExtensions = apszTABExtensions;
        }
        const char *const *papszIter = papszExtensions;
        while (*papszIter)
        {
            std::string osFile =
                CPLResetExtensionSafe(GetDescription(), *papszIter);
            if (VSIStatL(osFile.c_str(), &sStatBuf) != 0)
            {
                osFile = CPLResetExtensionSafe(GetDescription(),
                                               CPLString(*papszIter).toupper());
                if (VSIStatL(osFile.c_str(), &sStatBuf) != 0)
                {
                    osFile.clear();
                }
            }
            if (!osFile.empty())
                osList.AddString(osFile.c_str());
            papszIter++;
        }
    }
    return osList.StealList();
}

/************************************************************************/
/*                            ExecuteSQL()                              */
/************************************************************************/

OGRLayer *OGRTABDataSource::ExecuteSQL(const char *pszStatement,
                                       OGRGeometry *poSpatialFilter,
                                       const char *pszDialect)
{
    char **papszTokens = CSLTokenizeString(pszStatement);
    if (CSLCount(papszTokens) == 6 && EQUAL(papszTokens[0], "CREATE") &&
        EQUAL(papszTokens[1], "INDEX") && EQUAL(papszTokens[2], "ON") &&
        EQUAL(papszTokens[4], "USING"))
    {
        IMapInfoFile *poLayer =
            dynamic_cast<IMapInfoFile *>(GetLayerByName(papszTokens[3]));
        if (poLayer == nullptr)
        {
            CPLError(CE_Failure, CPLE_AppDefined,
                     "`%s' failed failed, no such layer as `%s'.", pszStatement,
                     papszTokens[3]);
            CSLDestroy(papszTokens);
            return nullptr;
        }
        int nFieldIdx = poLayer->GetLayerDefn()->GetFieldIndex(papszTokens[5]);
        CSLDestroy(papszTokens);
        if (nFieldIdx < 0)
        {
            CPLError(CE_Failure, CPLE_AppDefined,
                     "`%s' failed, field not found.", pszStatement);
            return nullptr;
        }
        poLayer->SetFieldIndexed(nFieldIdx);
        return nullptr;
    }

    CSLDestroy(papszTokens);
    return GDALDataset::ExecuteSQL(pszStatement, poSpatialFilter, pszDialect);
}
