# map-shorts 🗺️🎬

**Seslendirmeden profesyonel harita animasyonlu Shorts üreten yapay zekâ skill'i.**
*An AI-agent skill that turns a narration into a fluid, satellite-map animated vertical video.*

Uydu haritası, sinematik kamera uçuşları, 3D dünya, çizilerek beliren sınırlar, rotalar,
gemiler, bayraklar, sayaçlar, minimal başlıklar ve ses efektleri — hepsi kodla çizilir
ve `ffmpeg` ile 1080×1920 / 60 fps render edilir. Ajan (Claude, Gemini, GPT/Codex, …)
metni okur, sahne sahne görselleri planlar, `scene.py` yazar, kareleri kontrol eder ve
videoyu üretir.

<p align="center">
  <img src="docs/media/macellan_intro.webp" width="200" alt="Dünyadan İspanya'ya: filo yola çıkıyor">
  <img src="docs/media/macellan_bogaz.webp" width="200" alt="Macellan Boğazı">
  <img src="docs/media/turkiye_gercek_boyut.webp" width="200" alt="Türkiye Almanya'nın üzerinde">
  <img src="docs/media/macellan_finale.webp" width="200" alt="Dünya turu finali">
</p>

**Macellan–Elcano seferi** (54 sn, tamamı ajan tarafından kodlandı ve render edildi):

<p align="center"><img src="docs/media/macellan_frames.jpg" width="100%" alt="Macellan örnek kareler"></p>

**Türkiye'nin gerçek boyutu** (29 sn):

<p align="center"><img src="docs/media/turkiye_frames.jpg" width="100%" alt="Türkiye gerçek boyut örnek kareler"></p>

> Önizlemeler sessiz ve küçültülmüştür; gerçek çıktı 1080×1920, 60 fps, seslendirme + efektli MP4'tür.

| Örnek | Konu |
|---|---|
| `examples/macellan` | Macellan–Elcano seferi: dünya → İspanya, filo, Macellan Boğazı, Pasifik, Filipinler, dönüş, dünya turu finali |
| `examples/turkiye_gercek_boyut` | Türkiye'nin gerçek boyutu: Almanya/Teksas karşılaştırması, Mercator bozulması |

## Kurulum / Install

**Linux / macOS**
```bash
git clone https://github.com/ozguryrr-design/map-shorts.git
cd map-shorts
bash scripts/setup.sh          # Python venv, bağımlılıklar, Natural Earth verisi, fontlar
```
Gerekenler: Python 3.10+, ffmpeg, cairo kütüphanesi.

**Windows (PowerShell, WSL gerekmez)**
```powershell
winget install Python.Python.3.12    # yoksa; python.org kurulumunda "Add python.exe to PATH" işaretleyin
git clone https://github.com/ozguryrr-design/map-shorts.git
cd map-shorts
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -InstallFfmpeg
```
`-InstallFfmpeg` ffmpeg'i winget ile kurar (zaten kuruluysa atlanır). Cairo ayrıca kurulmaz:
pycairo Windows'ta hazır paket (wheel) olarak gelir. Microsoft Store Python'u yerine python.org /
winget Python'unu kullanın. Git Bash kullanıyorsanız `bash scripts/setup.sh` de çalışır.

### Ajanınıza tanıtın / Register with your agent
Klasörün kendisi bir skill'dir (`SKILL.md`). Bu klasörü ajanınızın skill dizinine koyun / bağlayın:

| Ajan | Konum |
|---|---|
| Claude Code | `~/.claude/skills/map-shorts` (veya proje içinde `.claude/skills/map-shorts`) |
| OpenAI Codex CLI | `~/.codex/skills/map-shorts` — ya da depo içindeki `AGENTS.md` otomatik okunur |
| Google Antigravity | çalışma alanında `.agents/skills/map-shorts` |
| Gemini CLI, Cursor, diğerleri | depoyu açın ve ajana: *"SKILL.md'yi oku ve uygula"* deyin (`AGENTS.md` de yönlendirir) |

```bash
ln -s "$(pwd)" ~/.claude/skills/map-shorts     # örnek (Linux/macOS)
```
```powershell
# Windows (yönetici izni gerektirmeyen dizin bağlantısı)
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
New-Item -ItemType Junction -Path "$HOME\.claude\skills\map-shorts" -Target (Get-Location)
```

## Kullanım / Usage
Ajana sadece şunu söyleyin:

> "Bu seslendirme metni için harita videosu hazırla: *20 Eylül 1519. Beş gemi…*"

Seslendirmeniz varsa `projects/<ad>/vo/voice.mp3` olarak verin; yoksa ajan geçici bir
yapay zekâ sesi ile çalışır, sesinizi sonra eklediğinizde animasyonlar kelimelere göre
otomatik yeniden hizalanır.

Elle kullanım:
```bash
.venv/bin/python make.py new  benim_videom --text-str "Metin..."
.venv/bin/python make.py tts  benim_videom          # ya da: vo/voice.mp3 + make.py align
.venv/bin/python make.py sheet benim_videom         # önizleme kontak sayfası
.venv/bin/python make.py final benim_videom         # -> out/benim_videom.mp4
```
Windows'ta (PowerShell) `.venv/bin/python` yerine `.venv\Scripts\python` yazın:
```powershell
.venv\Scripts\python make.py final benim_videom
```

## Nasıl çalışır / How it works
* `mapengine/` — Python + Cairo çizim motoru (Web Mercator, uydu karoları, van Wijk kamera uçuşları,
  ortografik dünya, deniz rotası A* bulucu, efektler, prosedürel ses, paralel/devam edebilen render).
* Zamanlama kelimelere bağlıdır: `w("Pasifik")` — ses değişse de sahne kaymaz.
* `references/` — ajan için API, stil rehberi ve sahne tarifleri.

## Lisanslar / Credits
Varsayılan ayarlarla üretilen video **para kazanılan kanallarda da kullanılabilir**: uydu altlığı
ticari kullanıma açık bir kaynaktan gelir ve gereken kaynak yazısı videoya otomatik eklenir.

### Uydu altlığı seçenekleri (`scene.py` içinde `TILE_PROVIDER`)
| Değer | Kaynak | Lisans | Ticari kullanım | Not |
|---|---|---|---|---|
| `"s2"` **(varsayılan)** | EOxCloudless Sentinel-2, **2016** | CC BY 4.0 | ✅ kaynak yazısı videoda görünür olmalı | Şehir ölçeğine kadar iyi; 2016 görüntüsü |
| `"nasa"` | NASA Blue Marble (GIBS) | Kamu malı (NASA) | ✅ "NASA" kaynak olarak belirtilmeli | Düşük çözünürlük: dünya küresi / kıta görünümleri için |
| `"esri"` | Esri World Imagery | Esri kullanım şartları | ❌ yalnızca kişisel / ticari olmayan | En keskin görüntü; para kazanılan videoda kullanmayın |

* **Kaynak yazısı otomatik:** her karenin sol üst köşesine küçük, yarı saydam bir kaynak satırı
  çizilir (Shorts arayüzünün ve başlıkların dışında). EOX'in CC BY şartı, videolarda kaynağın
  **videonun üzerinde görünmesini** istediği için `"s2"` ile `ATTRIBUTION = True` açık kalmalıdır.
* **Açıklama metni:** `make.py final` ayrıca `out/<ad>_credits.txt` üretir; video açıklamasına
  yapıştırın (`make.py credits <ad>` ile ayrıca da alınabilir).
* `"esri"` seçilirse render sırasında ticari kullanım uyarısı basılır.
* EOX'in 2017 ve sonraki yıllık katmanları ticari olmayan (CC BY-NC-SA) / ücretlidir; kod bilerek
  yalnızca CC BY 4.0 olan **2016** katmanını kullanır.

### Diğer bileşenler
* Kod: MIT.
* Sınır verisi: [Natural Earth](https://www.naturalearthdata.com/) (public domain).
* Font: Montserrat (SIL OFL). Bayraklar: flagcdn.com (ulusal bayraklar).
* **Geçici ses (edge-tts) yalnızca taslak içindir:** Microsoft Edge'in sesini resmî olmayan yoldan
  kullanır. Yayınlamadan önce kendi sesinizi `vo/voice.mp3` olarak koyup `make.py align` çalıştırın;
  `credits.txt` geçici ses kullanıldıysa uyarır. Hizalama: faster-whisper (MIT).

> Bu bölüm bilgilendirme amaçlıdır, hukuki tavsiye değildir. Lisans şartları değişebilir:
> [EOxCloudless lisansı](https://cloudless.eox.at/documentation/license),
> [NASA medya kullanım kuralları](https://www.nasa.gov/nasa-brand-center/images-and-media/).
