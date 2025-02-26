/*-*-C++-*-*/
/******************************************************************************
 *
 * Project:  TIGER/Line Translator
 * Purpose:  Main declarations for Tiger translator.
 * Author:   Frank Warmerdam, warmerdam@pobox.com
 *
 ******************************************************************************
 * Copyright (c) 1999, Frank Warmerdam
 * Copyright (c) 2008-2011, Even Rouault <even dot rouault at spatialys.com>
 *
 * SPDX-License-Identifier: MIT
 ****************************************************************************/

#ifndef OGR_TIGER_H_INCLUDED
#define OGR_TIGER_H_INCLUDED

#include "cpl_conv.h"
#include "ogrsf_frmts.h"

class OGRTigerDataSource;

/*
** TIGER Versions
**
** 0000           TIGER/Line Precensus Files, 1990
** 0002           TIGER/Line Initial Voting District Codes Files, 1990
** 0003           TIGER/Line Files, 1990
** 0005           TIGER/Line Files, 1992
** 0021           TIGER/Line Files, 1994
** 0024           TIGER/Line Files, 1995
** 0697 to 1098   TIGER/Line Files, 1997
** 1298 to 0499   TIGER/Line Files, 1998
** 0600 to 0800   TIGER/Line Files, 1999
** 1000 to 1100   TIGER/Line Files, Redistricting Census 2000
** 0301 to 0801   TIGER/Line Files, Census 2000
**
** 0302 to 0502   TIGER/Line Files, UA 2000
** ????    ????
**
** 0602  & higher TIGER/Line Files, 2002
** ????    ????
*/

typedef enum
{
    TIGER_1990_Precensus = 0,
    TIGER_1990 = 1,
    TIGER_1992 = 2,
    TIGER_1994 = 3,
    TIGER_1995 = 4,
    TIGER_1997 = 5,
    TIGER_1998 = 6,
    TIGER_1999 = 7,
    TIGER_2000_Redistricting = 8,
    TIGER_2000_Census = 9,
    TIGER_UA2000 = 10,
    TIGER_2002 = 11,
    TIGER_2003 = 12,
    TIGER_2004 = 13,
    TIGER_Unknown
} TigerVersion;

TigerVersion TigerClassifyVersion(int);
const char *TigerVersionString(TigerVersion);

/*****************************************************************************/
/* The TigerFieldInfo and TigerRecordInfo structures hold information about  */
/* the schema of a TIGER record type.  In each layer implementation file     */
/* there are statically initialized variables of these types that describe    */
/* the record types associated with that layer.  In the case where different */
/* TIGER versions have different schemas, there is a                         */
/* TigerFieldInfo/TigerRecordInfo for each version, and the constructor      */
/* for the layer chooses a pointer to the correct set based on the version.  */
/*****************************************************************************/

typedef struct TigerFieldInfo
{
    char pszFieldName[11];  // name of the field
    char cFmt;              // format of the field ('L' or 'R')
    char cType;             // type of the field ('A' or 'N')
    char OGRtype;        // OFTType of the field (OFTInteger, OFTString, ...?)
    unsigned char nBeg;  // beginning column number for field
    unsigned char nEnd;  // ending column number for field
    unsigned char nLen;  // length of field

    unsigned int bDefine : 1;  // whether to add this field to the FeatureDefn
    unsigned int bSet : 1;     // whether to set this field in GetFeature()
} TigerFieldInfo;

typedef struct TigerRecordInfo
{
    const TigerFieldInfo *pasFields;
    unsigned char nFieldCount;
    unsigned char nRecordLength;
} TigerRecordInfo;

// OGR_TIGER_RECBUF_LEN should be a number that is larger than the
// longest possible record length for any record type; it is used to
// create arrays to hold the records.  At the time of this writing the
// longest record (RT1) has length 228, but I'm choosing 500 because
// it is a good round number and will allow for growth without having
// to modify this file.  The code never holds more than a few records
// in memory at a time, so having OGR_TIGER_RECBUF_LEN be much larger
// than is really necessary won't affect the amount of memory required
// in a substantial way.
// mbp Fri Dec 20 19:19:59 2002
// Note: OGR_TIGER_RECBUF_LEN should also be larger than 255, since
// TigerRecordInfo::nRecordLength fits on unsigned char.
#define OGR_TIGER_RECBUF_LEN 500

/************************************************************************/
/*                            TigerFileBase                             */
/************************************************************************/

class TigerFileBase CPL_NON_FINAL
{
  protected:
    OGRTigerDataSource *poDS;

    char *pszModule;
    char *pszShortModule;
    VSILFILE *fpPrimary;

    OGRFeatureDefn *poFeatureDefn;

    int nFeatures;
    int nRecordLength;

    int OpenFile(const char *, const char *);
    void EstablishFeatureCount();

    static int EstablishRecordLength(VSILFILE *);

    void SetupVersion();

    int nVersionCode;
    TigerVersion nVersion;

  public:
    explicit TigerFileBase(const TigerRecordInfo *psRTInfoIn = nullptr,
                           const char *m_pszFileCodeIn = nullptr);
    virtual ~TigerFileBase();

    TigerVersion GetVersion()
    {
        return nVersion;
    }

    int GetVersionCode()
    {
        return nVersionCode;
    }

    virtual const char *GetShortModule()
    {
        return pszShortModule;
    }

    virtual const char *GetModule()
    {
        return pszModule;
    }

    virtual int GetFeatureCount()
    {
        return nFeatures;
    }

    OGRFeatureDefn *GetFeatureDefn()
    {
        return poFeatureDefn;
    }

    static const char *GetField(const char *, int, int);
    static void SetField(OGRFeature *, const char *, const char *, int, int);

    virtual bool SetModule(const char *pszModule);
    virtual OGRFeature *GetFeature(int nRecordId);

  protected:
    static void AddFieldDefns(const TigerRecordInfo *psRTInfo,
                              OGRFeatureDefn *poFeatureDefn);

    static void SetFields(const TigerRecordInfo *psRTInfo,
                          OGRFeature *poFeature, char *achRecord);

    const TigerRecordInfo *psRTInfo;
    const char *m_pszFileCode;
};

/************************************************************************/
/*                          TigerCompleteChain                          */
/************************************************************************/

class TigerCompleteChain final : public TigerFileBase
{
    VSILFILE *fpShape;
    int *panShapeRecordId;

    VSILFILE *fpRT3;
    bool bUsingRT3;
    int nRT1RecOffset;

    int GetShapeRecordId(int, int);
    bool AddShapePoints(int, int, OGRLineString *, int);

    void AddFieldDefnsPre2002();
    OGRFeature *GetFeaturePre2002(int);

    OGRFeature *GetFeature2002(int);
    void AddFieldDefns2002();

    const TigerRecordInfo *psRT1Info;
    const TigerRecordInfo *psRT2Info;
    const TigerRecordInfo *psRT3Info;

  public:
    TigerCompleteChain(OGRTigerDataSource *, const char *);
    virtual ~TigerCompleteChain();

    virtual bool SetModule(const char *) override;

    virtual OGRFeature *GetFeature(int) override;
};

/************************************************************************/
/*                    TigerAltName (Type 4 records)                     */
/************************************************************************/

class TigerAltName final : public TigerFileBase
{
  public:
    TigerAltName(OGRTigerDataSource *, const char *);

    virtual OGRFeature *GetFeature(int) override;
};

/************************************************************************/
/*                    TigerFeatureIds (Type 5 records)                  */
/************************************************************************/

class TigerFeatureIds final : public TigerFileBase
{
  public:
    TigerFeatureIds(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                    TigerZipCodes (Type 6 records)                    */
/************************************************************************/

class TigerZipCodes final : public TigerFileBase
{
  public:
    TigerZipCodes(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                    TigerPoint                                        */
/* This is an abstract base class for TIGER layers with point geometry. */
/* Since much of the implementation of these layers is similar, I've    */
/* put it into this base class to avoid duplication in the actual       */
/* layer classes.  mbp Sat Jan  4 16:41:19 2003.                        */
/************************************************************************/

class TigerPoint CPL_NON_FINAL : public TigerFileBase
{
  protected:
    explicit TigerPoint(const TigerRecordInfo *psRTInfoIn = nullptr,
                        const char *m_pszFileCodeIn = nullptr);

  public:
    virtual OGRFeature *GetFeature(int nFID) override
    {
        return TigerFileBase::GetFeature(nFID);
    } /* to avoid -Woverloaded-virtual warnings */

    OGRFeature *GetFeature(int nRecordId, int nX0, int nX1, int nY0, int nY1);
};

/************************************************************************/
/*                   TigerLandmarks (Type 7 records)                    */
/************************************************************************/

class TigerLandmarks final : public TigerPoint
{
  public:
    TigerLandmarks(OGRTigerDataSource *, const char *);

    virtual OGRFeature *GetFeature(int) override;
};

/************************************************************************/
/*                   TigerAreaLandmarks (Type 8 records)                */
/************************************************************************/

class TigerAreaLandmarks final : public TigerFileBase
{
  public:
    TigerAreaLandmarks(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                   TigerKeyFeatures (Type 9 records)                  */
/************************************************************************/

class TigerKeyFeatures final : public TigerFileBase
{
  public:
    TigerKeyFeatures(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                   TigerPolygon (Type A&S records)                    */
/************************************************************************/

class TigerPolygon final : public TigerFileBase
{
  private:
    const TigerRecordInfo *psRTAInfo;
    const TigerRecordInfo *psRTSInfo;

    VSILFILE *fpRTS;
    bool bUsingRTS;
    int nRTSRecLen;

  public:
    TigerPolygon(OGRTigerDataSource *, const char *);
    virtual ~TigerPolygon();

    virtual bool SetModule(const char *) override;

    virtual OGRFeature *GetFeature(int) override;
};

/************************************************************************/
/*                    TigerPolygonCorrections (Type B records)          */
/************************************************************************/

class TigerPolygonCorrections final : public TigerFileBase
{
  public:
    TigerPolygonCorrections(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                  TigerEntityNames (Type C records)                   */
/************************************************************************/

class TigerEntityNames final : public TigerFileBase
{
  public:
    TigerEntityNames(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                    TigerPolygonEconomic (Type E records)             */
/************************************************************************/

class TigerPolygonEconomic final : public TigerFileBase
{
  public:
    TigerPolygonEconomic(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                  TigerIDHistory (Type H records)                     */
/************************************************************************/

class TigerIDHistory final : public TigerFileBase
{
  public:
    TigerIDHistory(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                   TigerPolyChainLink (Type I records)                */
/************************************************************************/

class TigerPolyChainLink final : public TigerFileBase
{
  public:
    TigerPolyChainLink(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                TigerSpatialMetadata (Type M records)                 */
/************************************************************************/

class TigerSpatialMetadata final : public TigerFileBase
{
  public:
    TigerSpatialMetadata(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                   TigerPIP (Type P records)                          */
/************************************************************************/

class TigerPIP final : public TigerPoint
{
  public:
    TigerPIP(OGRTigerDataSource *, const char *);

    virtual OGRFeature *GetFeature(int) override;
};

/************************************************************************/
/*                   TigerTLIDRange (Type R records)                    */
/************************************************************************/

class TigerTLIDRange final : public TigerFileBase
{
  public:
    TigerTLIDRange(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                    TigerZeroCellID (Type T records)                  */
/************************************************************************/

class TigerZeroCellID final : public TigerFileBase
{
  public:
    TigerZeroCellID(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                    TigerOverUnder (Type U records)                   */
/************************************************************************/

class TigerOverUnder final : public TigerPoint
{
  public:
    TigerOverUnder(OGRTigerDataSource *, const char *);

    virtual OGRFeature *GetFeature(int) override;
};

/************************************************************************/
/*                    TigerZipPlus4 (Type Z records)                    */
/************************************************************************/

class TigerZipPlus4 final : public TigerFileBase
{
  public:
    TigerZipPlus4(OGRTigerDataSource *, const char *);
};

/************************************************************************/
/*                            OGRTigerLayer                             */
/************************************************************************/

class OGRTigerLayer final : public OGRLayer
{
    TigerFileBase *poReader;

    OGRTigerDataSource *poDS;

    int nFeatureCount;
    int *panModuleFCount;
    int *panModuleOffset;

    int iLastFeatureId;
    int iLastModule;

  public:
    OGRTigerLayer(OGRTigerDataSource *poDS, TigerFileBase *);
    virtual ~OGRTigerLayer();

    void ResetReading() override;
    OGRFeature *GetNextFeature() override;
    OGRFeature *GetFeature(GIntBig nFeatureId) override;

    OGRFeatureDefn *GetLayerDefn() override;

    GIntBig GetFeatureCount(int) override;

    int TestCapability(const char *) override;
};

/************************************************************************/
/*                          OGRTigerDataSource                          */
/************************************************************************/

class OGRTigerDataSource final : public GDALDataset
{
    int nLayers;
    OGRTigerLayer **papoLayers;

    OGRSpatialReference *poSpatialRef;

    char **papszOptions;

    char *pszPath;

    int nModules;
    char **papszModules;

    int nVersionCode;
    TigerVersion nVersion;

    TigerVersion TigerCheckVersion(TigerVersion, const char *);

    CPL_DISALLOW_COPY_ASSIGN(OGRTigerDataSource)

  public:
    OGRTigerDataSource();
    virtual ~OGRTigerDataSource();

    TigerVersion GetVersion() const
    {
        return nVersion;
    }

    int GetVersionCode() const
    {
        return nVersionCode;
    }

    const char *GetOption(const char *);

    int Open(const char *pszName, int bTestOpen = FALSE,
             char **papszFileList = nullptr);

    int GetLayerCount() override;
    OGRLayer *GetLayer(int) override;
    OGRLayer *GetLayer(const char *pszLayerName);

    void AddLayer(OGRTigerLayer *);

    OGRSpatialReference *DSGetSpatialRef()
    {
        return poSpatialRef;
    }

    const char *GetDirPath()
    {
        return pszPath;
    }

    char *BuildFilename(const char *pszModule, const char *pszExtension);

    int GetModuleCount() const
    {
        return nModules;
    }

    const char *GetModule(int);
    bool CheckModule(const char *pszModule);
    void AddModule(const char *pszModule);
};

#endif /* ndef OGR_TIGER_H_INCLUDED */
