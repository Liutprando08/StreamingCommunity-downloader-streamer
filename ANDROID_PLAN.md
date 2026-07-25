# StreamingCommunity Android - Piano di Implementazione

## Architettura

```
app/src/main/
├── data/
│   ├── remote/
│   │   ├── scrapers/
│   │   │   ├── YtsScraper.kt
│   │   │   ├── EztvScraper.kt
│   │   │   ├── NyaaScraper.kt
│   │   │   ├── LimeTorrentScraper.kt
│   │   │   ├── TorrentGalaxyScraper.kt
│   │   │   └── BaseScraper.kt
│   │   ├── Interceptors/
│   │   │   └── CloudFlareInterceptor.kt
│   │   └── ApiService.kt
│   ├── local/
│   │   ├── ConfigDataStore.kt
│   │   ├── DownloadDatabase.kt
│   │   └── DownloadDao.kt
│   └── repository/
│       ├── TorrentRepository.kt
│       ├── ConfigRepository.kt
│       └── DownloadRepository.kt
├── domain/
│   ├── model/
│   │   ├── TorrentResult.kt
│   │   ├── DownloadState.kt
│   │   ├── MediaEntry.kt
│   │   └── Config.kt
│   ├── usecase/
│   │   ├── SearchTorrentUseCase.kt
│   │   ├── DownloadTorrentUseCase.kt
│   │   ├── MuxAudioUseCase.kt
│   │   └── GetDownloadHistoryUseCase.kt
│   └── repository/
│       ├── ITorrentRepository.kt
│       └── IConfigRepository.kt
├── ui/
│   ├── theme/
│   │   ├── Color.kt
│   │   ├── Theme.kt
│   │   └── Type.kt
│   ├── navigation/
│   │   └── NavGraph.kt
│   ├── screens/
│   │   ├── HomeScreen.kt
│   │   ├── SearchScreen.kt
│   │   ├── ResultsScreen.kt
│   │   ├── DownloadScreen.kt
│   │   ├── PlayerScreen.kt
│   │   └── SettingsScreen.kt
│   ├── components/
│   │   ├── TorrentCard.kt
│   │   ├── SearchBar.kt
│   │   ├── DownloadProgress.kt
│   │   ├── QualityBadge.kt
│   │   └── EmptyState.kt
│   └── viewmodel/
│       ├── SearchViewModel.kt
│       ├── DownloadViewModel.kt
│       └── SettingsViewModel.kt
├── di/
│   ├── NetworkModule.kt
│   ├── DatabaseModule.kt
│   ├── RepositoryModule.kt
│   └── UseCaseModule.kt
├── service/
│   ├── TorrentDownloadService.kt
│   └── MuxService.kt
└── util/
    ├── Extensions.kt
    ├── QualityParser.kt
    ├── SeasonEpisodeParser.kt
    └── FileHelper.kt
```

---

## Mappatura Python → Kotlin

| Componente | Python | Kotlin Android |
|------------|--------|----------------|
| HTTP Client | `curl_cffi` | `OkHttp` + `CloudFlareInterceptor` |
| HTML Parser | `BeautifulSoup` | `Jsoup` |
| JSON | `json` | `kotlinx.serialization` |
| XML | `xml.etree.ElementTree` | `kotlinx.serialization` |
| Torrent | `aria2c` (subprocess) | `libtorrent4j` |
| Mux | `ffmpeg` (subprocess) | `ffmpeg-kit` |
| Config | `config.json` | `DataStore<Preferences>` |
| DB | nessuno | `Room` |
| UI | `rich` (CLI) | `Jetpack Compose` + Material3 |
| DI | nessuno | `Hilt` |
| Async | `threading` | `Kotlin Coroutines` + `Flow` |

---

## Dipendenze

```kotlin
// build.gradle.kts (app)

dependencies {
    // Core
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("androidx.activity:activity-compose:1.8.2")

    // Compose
    implementation(platform("androidx.compose:compose-bom:2024.02.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.navigation:navigation-compose:2.7.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")

    // Network
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("org.jsoup:jsoup:1.17.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.0")

    // Torrent
    implementation("org.libtorrent4j:libtorrent4j:2.0.7")

    // FFmpeg
    implementation("com.arthenica:ffmpeg-kit-full:6.0-2")

    // DI (Hilt)
    implementation("com.google.dagger:hilt-android:2.50")
    kapt("com.google.dagger:hilt-compiler:2.50")
    implementation("androidx.hilt:hilt-navigation-compose:1.1.0")

    // Room (storico download)
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    kapt("androidx.room:room-compiler:2.6.1")

    // DataStore (config)
    implementation("androidx.datastore:datastore-preferences:1.0.0")

    // Image loading
    implementation("io.coil-kt:coil-compose:2.5.0")
}
```

---

## Fasi di Implementazione

### Fase 1: Setup Progetto (1-2 giorni)

- [ ] Creare progetto Android con Kotlin + Compose
- [ ] Configurare Hilt per DI
- [ ] Setup Navigation (NavGraph)
- [ ] Creare Theme Material3
- [ ] Struttura package (data, domain, ui, di)

### Fase 2: Modelli e Interfacce (1 giorno)

- [ ] `TorrentResult.kt` - modello dati torrent
- [ ] `DownloadState.kt` - stati download (Idle, Downloading, Muxing, Done, Error)
- [ ] `MediaEntry.kt` - modello entry media
- [ ] `Config.kt` - modello configurazione
- [ ] Interfacce repository

### Fase 3: Scrapers (2-3 giorni)

- [ ] `BaseScraper.kt` - classe base con metodi comuni
  - `_parseSize(text: String): Long`
  - `_extractQuality(title: String): String`
  - `_extractYear(title: String): Int?`
  - `_buildMagnet(infoHash: String, title: String): String`
- [ ] `YtsScraper.kt` - API JSON diretta
- [ ] `EztvScraper.kt` - API JSON + TMDB lookup
- [ ] `NyaaScraper.kt` - RSS XML parsing
- [ ] `LimeTorrentScraper.kt` - HTML parsing + mirror failover
- [ ] `TorrentGalaxyScraper.kt` - HTML parsing + mirror failover
- [ ] `CloudFlareInterceptor.kt` - bypass Cloudflare con impersonation

### Fase 4: Download Manager (2-3 giorni)

- [ ] `TorrentDownloadService.kt` - servizio Android in background
  - Inizializzare sessione libtorrent4j
  - Aggiungere torrent da magnet URL
  - Monitorare stato download
  - Notifiche progresso
- [ ] `DownloadState` flow per UI updates
- [ ] Gestione permessi storage
- [ ] Cleanup automatico file temporanei

### Fase 5: Muxer (1 giorno)

- [ ] `MuxService.kt` - wrapper ffmpeg-kit
  - Rilevare stream video/audio
  - Mux video torrent + audio italiano
  - Preservare audio originale
  - Metadata lingua
- [ ] Disk space check prima del mux
- [ ] Timeout e gestione errori

### Fase 6: Config e Database (1-2 giorni)

- [ ] `ConfigDataStore.kt` - DataStore per preferenze
  - `torrentEnabled: Boolean`
  - `preferredQuality: String`
  - `autoMux: Boolean`
  - `scrapeDelay: Int`
  - `scrapeRetries: Int`
- [ ] `DownloadDatabase.kt` - Room DB per storico
  - Tabella `downloads` (id, title, path, date, status)
  - Query: getAll, getByTitle, insert, delete
- [ ] `SettingsViewModel.kt` - gestione impostazioni UI

### Fase 7: UI (3-4 giorni)

- [ ] `HomeScreen.kt` - schermata iniziale
  - Griglia categorie (Film, Serie, Anime, Torrent)
  - Ricerca rapida
- [ ] `SearchScreen.kt` - barra ricerca + risultati
  - SearchBar con historico
  - Filtro per tipo (film/serie)
- [ ] `ResultsScreen.kt` - lista risultati torrent
  - `TorrentCard` con titolo, qualit, seeders, dimensione
  - Tap per dettagli/download
  - Sorting per seeders/qualit
- [ ] `DownloadScreen.kt` - gestione download
  - Lista download attivi con progress bar
  - Stato: Scaricando → Muxing → Completato
  - Pausa/Annulla/Riprova
- [ ] `PlayerScreen.kt` - player video
  - ExoPlayer con controlli base
  - Selezione traccia audio (originale + italiano)
- [ ] `SettingsScreen.kt` - impostazioni
  - Toggle torrent enabled
  - Selezione qualit preferita
  - Auto-mux toggle
  - Info spazio disco

### Fase 8: Background Service (1 giorno)

- [ ] `TorrentDownloadService.kt` - Foreground Service
  - Notification channel per download
  - Progress bar nella notifica
  - Wake lock per download in background
  - Restart automatico se ucciso

### Fase 9: Test (2-3 giorni)

- [ ] Unit test scrapers
- [ ] Unit test use cases
- [ ] Integration test download flow
- [ ] UI test con Compose testing

---

## Pattern di Architettura

### Repository Pattern
```kotlin
// Interface
interface ITorrentRepository {
    suspend fun search(query: String): List<TorrentResult>
    suspend fun download(magnet: String): Flow<DownloadState>
}

// Implementation
class TorrentRepository @Inject constructor(
    private val scrapers: Set<@JvmSuppressWildcards BaseScraper>,
    private val downloader: TorrentDownloader
) : ITorrentRepository {
    override suspend fun search(query: String): List<TorrentResult> {
        return scrapers.flatMap { it.search(query) }
            .sortedByDescending { it.seeders }
    }
}
```

### Use Case Pattern
```kotlin
class SearchTorrentUseCase @Inject constructor(
    private val repository: ITorrentRepository
) {
    suspend operator fun invoke(query: String): List<TorrentResult> {
        return repository.search(query)
    }
}
```

### ViewModel + StateFlow
```kotlin
@HiltViewModel
class SearchViewModel @Inject constructor(
    private val searchUseCase: SearchTorrentUseCase
) : ViewModel() {
    private val _uiState = MutableStateFlow(SearchUiState())
    val uiState: StateFlow<SearchUiState> = _uiState.asStateFlow()

    fun search(query: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true) }
            val results = searchUseCase(query)
            _uiState.update { it.copy(results = results, isLoading = false) }
        }
    }
}
```

---

## Timeline Stimata

| Fase | Giorni | Cumulativo |
|------|--------|------------|
| 1. Setup progetto | 1-2 | 1-2 |
| 2. Modelli e interfacce | 1 | 2-3 |
| 3. Scrapers | 2-3 | 4-6 |
| 4. Download manager | 2-3 | 6-9 |
| 5. Muxer | 1 | 7-10 |
| 6. Config e DB | 1-2 | 8-12 |
| 7. UI | 3-4 | 11-16 |
| 8. Background service | 1 | 12-17 |
| 9. Test | 2-3 | 14-20 |
| **Totale** | **14-20 giorni** | |

---

## Note Tecniche

### Libtorrent4j vs aTorrent

| | libtorrent4j | aTorrent |
|--|--------------|----------|
| Controllo | Pieno | Limitato |
| Magnet | Nativo | Nativo |
| Progresso | Granulare | Base |
| Complessit | Alta | Bassa |
| Raccomandato | Per controllo totale | Per semplicit |

### CloudFlare Bypass

```kotlin
// OkHttp Interceptor con impersonation
class CloudFlareInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request().newBuilder()
            .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...")
            .header("Accept", "text/html,application/xhtml+xml")
            .build()
        return chain.proceed(request)
    }
}
```

### Permessi Android

```xml
<!-- AndroidManifest.xml -->
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" 
    android:maxSdkVersion="28" />
<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
```
