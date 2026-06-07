/*
 * rimsort_steam.cpp — Minimal Steamworks SDK wrapper for RimSort
 *
 * Exposes only the ISteamUGC functions RimSort needs via extern "C" linkage
 * for consumption by Python ctypes. Compiles to a single shared library
 * (~250-300 LOC) linked against libsteam_api.
 *
 * Build: see Makefile (macOS/Linux) or build_windows.bat (Windows)
 */

#include "steam/steam_api.h"

#include <cstdint>
#include <cstring>

// Platform-specific export macro
#ifdef _WIN32
#define SW_PY extern "C" __declspec(dllexport)
#else
#define SW_PY extern "C" __attribute__((visibility("default")))
#endif

// --------------------------------------------------------------------------
// C-compatible result structs (must match Python ctypes definitions exactly)
// --------------------------------------------------------------------------

struct SubscriptionResult {
    int32_t result;
    uint64_t publishedFileId;
};

struct GetAppDependenciesResult {
    int32_t result;
    uint64_t publishedFileId;
    uint32_t* arrayAppDependencies;
    uint32_t arrayNumAppDependencies;
    uint32_t totalNumAppDependencies;
};

struct DownloadItemResult {
    uint32_t appId;
    uint64_t publishedFileId;
    int32_t result;
};

struct ItemInstalledResult {
    uint32_t appId;
    uint64_t publishedFileId;
    uint64_t legacyContent;
    uint64_t manifestId;
};

// --------------------------------------------------------------------------
// Callback function pointer types
// --------------------------------------------------------------------------

typedef void (*SubscriptionCallback_t)(SubscriptionResult);
typedef void (*AppDepsCallback_t)(GetAppDependenciesResult);
typedef void (*DownloadItemResultCallback_t)(DownloadItemResult);
typedef void (*ItemInstalledCallback_t)(ItemInstalledResult);

// --------------------------------------------------------------------------
// Workshop class — manages CCallResult/CCallback instances
// --------------------------------------------------------------------------

// RimWorld's Steam AppID for filtering global callbacks
static const uint32_t RIMWORLD_APP_ID = 294100;

class Workshop {
public:
    Workshop()
        : m_subscribeCallback(nullptr)
        , m_unsubscribeCallback(nullptr)
        , m_appDepsCallback(nullptr)
        , m_downloadItemResultCallback(nullptr)
        , m_itemInstalledCallback(nullptr)
        , m_cbDownloadItemResult(this, &Workshop::OnDownloadItemResult)
        , m_cbItemInstalled(this, &Workshop::OnItemInstalled)
    {}

    // Per-call async results (CCallResult)
    void SubscribeItem(uint64_t pfid) {
        SteamAPICall_t call = SteamUGC()->SubscribeItem(pfid);
        m_subscribeResult.Set(call, this, &Workshop::OnSubscribeItem);
    }

    void UnsubscribeItem(uint64_t pfid) {
        SteamAPICall_t call = SteamUGC()->UnsubscribeItem(pfid);
        m_unsubscribeResult.Set(call, this, &Workshop::OnUnsubscribeItem);
    }

    void GetAppDependencies(uint64_t pfid) {
        SteamAPICall_t call = SteamUGC()->GetAppDependencies(pfid);
        m_appDepsResult.Set(call, this, &Workshop::OnGetAppDependencies);
    }

    // Synchronous — returns bool immediately
    bool DownloadItem(uint64_t pfid, bool highPriority) {
        return SteamUGC()->DownloadItem(pfid, highPriority);
    }

    // Callback setters
    void SetSubscribeCallback(SubscriptionCallback_t cb) { m_subscribeCallback = cb; }
    void SetUnsubscribeCallback(SubscriptionCallback_t cb) { m_unsubscribeCallback = cb; }
    void SetAppDepsCallback(AppDepsCallback_t cb) { m_appDepsCallback = cb; }
    void SetDownloadItemResultCallback(DownloadItemResultCallback_t cb) { m_downloadItemResultCallback = cb; }
    void SetItemInstalledCallback(ItemInstalledCallback_t cb) { m_itemInstalledCallback = cb; }

private:
    // Python callback pointers
    SubscriptionCallback_t m_subscribeCallback;
    SubscriptionCallback_t m_unsubscribeCallback;
    AppDepsCallback_t m_appDepsCallback;
    DownloadItemResultCallback_t m_downloadItemResultCallback;
    ItemInstalledCallback_t m_itemInstalledCallback;

    // CCallResult instances (one per operation type)
    CCallResult<Workshop, RemoteStorageSubscribePublishedFileResult_t> m_subscribeResult;
    CCallResult<Workshop, RemoteStorageUnsubscribePublishedFileResult_t> m_unsubscribeResult;
    CCallResult<Workshop, GetAppDependenciesResult_t> m_appDepsResult;

    // CCallback handlers (declared via STEAM_CALLBACK macro)
    STEAM_CALLBACK(Workshop, OnDownloadItemResult, DownloadItemResult_t, m_cbDownloadItemResult);
    STEAM_CALLBACK(Workshop, OnItemInstalled, ItemInstalled_t, m_cbItemInstalled);

    // CCallResult handlers
    void OnSubscribeItem(RemoteStorageSubscribePublishedFileResult_t* pResult, bool bIOFailure) {
        if (m_subscribeCallback && !bIOFailure) {
            SubscriptionResult r;
            r.result = pResult->m_eResult;
            r.publishedFileId = pResult->m_nPublishedFileId;
            m_subscribeCallback(r);
        }
    }

    void OnUnsubscribeItem(RemoteStorageUnsubscribePublishedFileResult_t* pResult, bool bIOFailure) {
        if (m_unsubscribeCallback && !bIOFailure) {
            SubscriptionResult r;
            r.result = pResult->m_eResult;
            r.publishedFileId = pResult->m_nPublishedFileId;
            m_unsubscribeCallback(r);
        }
    }

    void OnGetAppDependencies(GetAppDependenciesResult_t* pResult, bool bIOFailure) {
        if (m_appDepsCallback && !bIOFailure) {
            GetAppDependenciesResult r;
            r.result = pResult->m_eResult;
            r.publishedFileId = pResult->m_nPublishedFileId;
            r.arrayAppDependencies = pResult->m_rgAppIDs;
            r.arrayNumAppDependencies = pResult->m_nNumAppDependencies;
            r.totalNumAppDependencies = pResult->m_nTotalNumAppDependencies;
            m_appDepsCallback(r);
        }
    }
};

// --------------------------------------------------------------------------
// CCallback handler implementations (outside the class for STEAM_CALLBACK)
// --------------------------------------------------------------------------

void Workshop::OnDownloadItemResult(DownloadItemResult_t* pResult) {
    if (pResult->m_unAppID != RIMWORLD_APP_ID) return;
    if (m_downloadItemResultCallback) {
        DownloadItemResult r;
        r.appId = pResult->m_unAppID;
        r.publishedFileId = pResult->m_nPublishedFileId;
        r.result = pResult->m_eResult;
        m_downloadItemResultCallback(r);
    }
}

void Workshop::OnItemInstalled(ItemInstalled_t* pResult) {
    if (pResult->m_unAppID != RIMWORLD_APP_ID) return;
    if (m_itemInstalledCallback) {
        ItemInstalledResult r;
        r.appId = pResult->m_unAppID;
        r.publishedFileId = pResult->m_nPublishedFileId;
        r.legacyContent = pResult->m_hLegacyContent;
        r.manifestId = pResult->m_unManifestID;
        m_itemInstalledCallback(r);
    }
}

// --------------------------------------------------------------------------
// Global state
// --------------------------------------------------------------------------

static bool g_initialized = false;
static Workshop* g_workshop = nullptr;

// --------------------------------------------------------------------------
// Exported functions
// --------------------------------------------------------------------------

// Lifecycle

SW_PY int RS_SteamAPI_Init() {
    if (g_initialized) return 0;

    if (!SteamAPI_Init()) return 1;

    if (!SteamUser()) {
        SteamAPI_Shutdown();
        return 2;
    }

    if (!SteamUser()->BLoggedOn()) {
        SteamAPI_Shutdown();
        return 3;
    }

    g_workshop = new Workshop();
    g_initialized = true;
    return 0;
}

SW_PY void RS_SteamAPI_Shutdown() {
    if (!g_initialized) return;
    delete g_workshop;
    g_workshop = nullptr;
    SteamAPI_Shutdown();
    g_initialized = false;
}

SW_PY void RS_SteamAPI_RunCallbacks() {
    if (g_initialized) {
        SteamAPI_RunCallbacks();
    }
}

SW_PY bool RS_SteamAPI_IsInitialized() {
    return g_initialized;
}

// Workshop operations

SW_PY void RS_Workshop_SubscribeItem(uint64_t pfid) {
    if (g_workshop) g_workshop->SubscribeItem(pfid);
}

SW_PY void RS_Workshop_UnsubscribeItem(uint64_t pfid) {
    if (g_workshop) g_workshop->UnsubscribeItem(pfid);
}

SW_PY void RS_Workshop_GetAppDependencies(uint64_t pfid) {
    if (g_workshop) g_workshop->GetAppDependencies(pfid);
}

SW_PY bool RS_Workshop_DownloadItem(uint64_t pfid, bool highPriority) {
    if (g_workshop) return g_workshop->DownloadItem(pfid, highPriority);
    return false;
}

// Callback registration

SW_PY void RS_Workshop_SetItemSubscribedCallback(SubscriptionCallback_t cb) {
    if (g_workshop) g_workshop->SetSubscribeCallback(cb);
}

SW_PY void RS_Workshop_SetItemUnsubscribedCallback(SubscriptionCallback_t cb) {
    if (g_workshop) g_workshop->SetUnsubscribeCallback(cb);
}

SW_PY void RS_Workshop_SetGetAppDependenciesResultCallback(AppDepsCallback_t cb) {
    if (g_workshop) g_workshop->SetAppDepsCallback(cb);
}

SW_PY void RS_Workshop_SetDownloadItemResultCallback(DownloadItemResultCallback_t cb) {
    if (g_workshop) g_workshop->SetDownloadItemResultCallback(cb);
}

SW_PY void RS_Workshop_SetItemInstalledCallback(ItemInstalledCallback_t cb) {
    if (g_workshop) g_workshop->SetItemInstalledCallback(cb);
}
