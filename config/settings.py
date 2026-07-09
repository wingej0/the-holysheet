"""
Environment-driven configuration. All secrets come from the .env file or
the host environment — nothing is hardcoded here.

Usage:
    from config.settings import DB, ASPIRE_LOGIN, ASPIRE_EXPORT
"""

import os
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@dataclass
class DatabaseSettings:
    host: str
    port: int
    name: str
    user: str
    password: str
    sslmode: str = ""

    @property
    def url(self) -> str:
        base = (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )
        if self.sslmode:
            base += f"?sslmode={self.sslmode}"
        return base


DB = DatabaseSettings(
    host=os.environ["DB_HOST"],
    port=int(os.environ.get("DB_PORT", 5432)),
    name=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    sslmode=os.environ.get("DB_SSLMODE", ""),
)


# ---------------------------------------------------------------------------
# Aspire SIS
# ---------------------------------------------------------------------------

@dataclass
class ExternalEndpoint:
    url: str
    headers: dict = field(default_factory=dict)
    payload: str | dict = ""


_ASPIRE_BASE_URL = os.environ.get("ASPIRE_BASE_URL", "https://aspire.example.com")

# ---------------------------------------------------------------------------
# Aspire login headers — browser fingerprint required so Aspire accepts the
# request. Referer points to the login page.
# ---------------------------------------------------------------------------
_ASPIRE_LOGIN_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": _ASPIRE_BASE_URL,
    "Referer": f"{_ASPIRE_BASE_URL}/Login.aspx",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
}

# ---------------------------------------------------------------------------
# Aspire export headers — Referer points to the export page itself.
# ---------------------------------------------------------------------------
_ASPIRE_EXPORT_HEADERS = {
    **_ASPIRE_LOGIN_HEADERS,
    "Referer": f"{_ASPIRE_BASE_URL}/StudentUtilities.aspx/StudentDemographicExport/Export",
}

# ---------------------------------------------------------------------------
# Aspire export payload — no secrets; field-inclusion toggles and school
# track IDs for this district. Update SelectedTrackIDs if schools change.
# ---------------------------------------------------------------------------
_ASPIRE_EXPORT_PAYLOAD = (
    "ElementarySchool=true&ElementarySchool=false&"
    "SelectedTrackIDs=11000514&SelectedTrackIDs=11000515&SelectedTrackIDs=11000516&"
    "SelectedTrackIDs=11000517&SelectedTrackIDs=11000518&SelectedTrackIDs=11000519&"
    "SelectedTrackIDs=11000520&SelectedTrackIDs=11000476&SelectedTrackIDs=11000479&"
    "SelectedTrackIDs=11000484&SelectedTrackIDs=11000441&SelectedTrackIDs=11000483&"
    "MiddleSchool=true&MiddleSchool=false&HighSchool=false&DistrictOffice=false&"
    "IncludeExited=false&IncludeNonAttenders=true&IncludeNonAttenders=false&"
    "IncludeLegalName=true&IncludeLegalName=false&IncludePreferredName=true&"
    "IncludePreferredName=false&IncludeAdvisor=true&IncludeAdvisor=false&"
    "IncludeBiliteracyAwards=true&IncludeBiliteracyAwards=false&"
    "IncludeBirthDate=true&IncludeBirthDate=false&IncludeBloodDegree=true&"
    "IncludeBloodDegree=false&IncludeImmigrant=true&IncludeImmigrant=false&"
    "IncludeCensusNumber=true&IncludeCensusNumber=false&IncludeContacts=true&"
    "IncludeContacts=false&IncludeEmergencyContacts=true&IncludeEmergencyContacts=false&"
    "IncludeDistrictOfResidence=true&IncludeDistrictOfResidence=false&"
    "IncludeEconomicallyDisadvantaged=true&IncludeEconomicallyDisadvantaged=false&"
    "IncludeELL=true&IncludeELL=false&IncludeEmailAddress=true&IncludeEmailAddress=false&"
    "IncludeEntryDate=true&IncludeEntryDate=false&IncludeEntryCode=true&"
    "IncludeEntryCode=false&IncludeEthnicity=true&IncludeEthnicity=false&"
    "IncludeExitDate=true&IncludeExitDate=false&IncludeExitCode=true&"
    "IncludeExitCode=false&IncludeEnrolledInUSSchool=true&IncludeEnrolledInUSSchool=false&"
    "IncludeImmigrantDate=true&IncludeImmigrantDate=false&IncludeFirstLanguage=true&"
    "IncludeFirstLanguage=false&IncludeForeignExchange=true&IncludeForeignExchange=false&"
    "IncludeFutureTrack=true&IncludeFutureTrack=false&IncludeGender=true&"
    "IncludeGender=false&IncludeGeoCode=true&IncludeGeoCode=false&"
    "IncludeGeoCodeName=true&IncludeGeoCodeName=false&IncludeGradeLevel=true&"
    "IncludeGradeLevel=false&IncludeGraduationYear=true&IncludeGraduationYear=false&"
    "IncludeHomeAddress=true&IncludeHomeAddress=false&IncludeHomeCommunicationLanguage=true&"
    "IncludeHomeCommunicationLanguage=false&IncludeHomeLanguageCode=true&"
    "IncludeHomeLanguageCode=false&IncludeHomeLanguage=true&IncludeHomeLanguage=false&"
    "IncludeHomeless=true&IncludeHomeless=false&IncludeIEPDisability=true&"
    "IncludeIEPDisability=false&IncludeIEPTimeCode=true&IncludeIEPTimeCode=false&"
    "IncludeIEPRegularPercent=true&IncludeIEPRegularPercent=false&"
    "IncludeIEPEnvironmentCode=true&IncludeIEPEnvironmentCode=false&"
    "IncludeCurrentlyUnderstandableLanguage=true&IncludeCurrentlyUnderstandableLanguage=false&"
    "IncludeLegalBindings=true&IncludeLegalBindings=false&IncludePrimaryLanguageCode=true&"
    "IncludePrimaryLanguageCode=false&IncludePrimaryLanguage=true&"
    "IncludePrimaryLanguage=false&IncludeMailingAddress=true&IncludeMailingAddress=false&"
    "IncludeMigrant=true&IncludeMigrant=false&IncludeMostUsedLanguage=true&"
    "IncludeMostUsedLanguage=false&IncludeNewStudentStatus=true&IncludeNewStudentStatus=false&"
    "IncludeOnTrackForGQ=true&IncludeOnTrackForGQ=false&IncludePhoneType=true&"
    "IncludePhoneType=false&IncludePhoneNumber=true&IncludePhoneNumber=false&"
    "IncludePreviousSchoolName=true&IncludePreviousSchoolName=false&"
    "IncludePreviousSchoolAddress=true&IncludePreviousSchoolAddress=false&"
    "IncludeRace=true&IncludeRace=false&IncludeResidentStatus=true&"
    "IncludeResidentStatus=false&IncludeReturningAfterExitingStatus=true&"
    "IncludeReturningAfterExitingStatus=false&IncludeSchoolCode=true&"
    "IncludeSchoolCode=false&IncludeSchoolName=true&IncludeSchoolName=false&"
    "IncludeSchoolOfResidence=true&IncludeSchoolOfResidence=false&"
    "IncludeSecondaryMathIIIOptOut=true&IncludeSecondaryMathIIIOptOut=false&"
    "IncludeTribalAffiliation=true&IncludeTribalAffiliation=false&"
    "IncludeBirthCertificate=true&IncludeBirthCertificate=false&"
    "IncludeUtahSchoolSystem=true&IncludeUtahSchoolSystem=false&"
    "IncludeYIC=true&IncludeYIC=false"
)

ASPIRE_LOGIN = ExternalEndpoint(
    url=f"{_ASPIRE_BASE_URL}/Login.aspx",
    headers=_ASPIRE_LOGIN_HEADERS,
    # Dict payload — requests handles URL-encoding of special characters in the password
    payload={
        "Username": os.environ["ASPIRE_USERNAME"],
        "Password": os.environ["ASPIRE_PASSWORD"],
    },
)

ASPIRE_EXPORT = ExternalEndpoint(
    url=f"{_ASPIRE_BASE_URL}/StudentUtilities.aspx/StudentDemographicExport/Export",
    headers=_ASPIRE_EXPORT_HEADERS,
    payload=_ASPIRE_EXPORT_PAYLOAD,
)


# ---------------------------------------------------------------------------
# Acadience Learning Online
# ---------------------------------------------------------------------------

_ACADIENCE_BASE_URL = "https://alo.acadiencelearning.org"
_ACADIENCE_DISTRICT_ID = os.environ.get("ACADIENCE_DISTRICT_ID", "1273")

_ACADIENCE_LOGIN_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": _ACADIENCE_BASE_URL,
}

_ACADIENCE_EXPORT_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
}

ACADIENCE_LOGIN = ExternalEndpoint(
    url=f"{_ACADIENCE_BASE_URL}/api/login",
    headers=_ACADIENCE_LOGIN_HEADERS,
    payload={
        "email": os.environ["ACADIENCE_EMAIL"],
        "password": os.environ["ACADIENCE_PASSWORD"],
    },
)


def acadience_export_url(year: str) -> str:
    """Construct Acadience benchmark export URL for a given year code (e.g. '24')."""
    return (
        f"{_ACADIENCE_BASE_URL}/api/districts/{_ACADIENCE_DISTRICT_ID}"
        f"/y/{year}/export-student-data/COMBINED_ENGLISH_K6_B"
    )


def acadience_pm_export_url(year: str) -> str:
    """Construct Acadience progress monitoring export URL for a given year code."""
    return (
        f"{_ACADIENCE_BASE_URL}/api/districts/{_ACADIENCE_DISTRICT_ID}"
        f"/y/{year}/export-student-data/COMBINED_ENGLISH_K12_PM"
    )


# ---------------------------------------------------------------------------
# SQL Server (Aspire backing database)
# ---------------------------------------------------------------------------

@dataclass
class SqlServerSettings:
    server: str
    database: str
    user: str
    password: str

    @property
    def url(self) -> str:
        return (
            f"mssql+pymssql://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.server}/{self.database}?charset=utf8"
        )


SQL_SERVER = SqlServerSettings(
    server=os.environ["SQL_SERVER"],
    database=os.environ["SQL_DATABASE"],
    user=os.environ["SQL_USERNAME"],
    password=os.environ["SQL_PASSWORD"],
)


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

GOOGLE_SERVICE_ACCOUNT_PATH = os.environ["GOOGLE_SERVICE_ACCOUNT_PATH"]
