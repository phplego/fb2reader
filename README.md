
FB2 Reader - Demo and Versions

Live demos:
- [fbReader_v1.1.html](fbReader_v1.1.html)
- [fbReader_v1.2.html](fbReader_v1.2.html)
- [fbReader_v1.3.0.html](fbReader_v1.3.0.html)
- [fbReader_v1.3.1.html](fbReader_v1.3.1.html)
- [fbReader_v1.3.3.html](fbReader_v1.3.3.html)
- [fbReader_v1.3.4.html](fbReader_v1.3.4.html)
- [fbAnalyzer_v1.0.html](fbAnalyzer_v1.0.html)

Summary of differences between versions:
- v1.1:
  - First public version. Russian UI (titles, labels).
  - Per-paragraph translation via OpenRouter; model is configurable; API key stored in localStorage.
  - Caches translations locally per file/language/paragraph; basic navigation (go to #para, go to last).
  - No TTS features.
- v1.2:
  - Adds the "compare" button to compare original and translated paragraphs side-by-side. (Parallel Dialog)
  - Refinements to the translator UI and parsing. Still Russian UI.
  - Keeps OpenRouter-based translation workflow and local caching.
  - No TTS features yet.
- v1.3.0:
  - Switch to English UI and title; adds a TTS settings modal and OpenAI TTS integration (calls https://api.openai.com/v1/audio/speech).
  - Retains OpenRouter translation and local caching.
- v1.3.1:
  - Adds audio integration around paragraphs: per-paragraph TTS generation and attaching playable audio elements; introduces deterministic local MP3 filenames via buildFilename(idx).
  - UI polish and controls for language selection and TTS model/voice; stores TTS-related settings in localStorage (openai_tts_key/model/voice).
- v1.3.3:
  - Improves local MP3 handling: auto-detects and attaches existing local audio files after rendering paragraphs using a reusable Audio probe (attachLocalAudioIfPresent).
  - Robustness fixes and small UX tweaks around audio playback and error handling.
- v1.3.4:
  - Add TTS Proxy support.

Notes:
- All versions use client-side localStorage; keys and cached translations never leave your browser except for API calls to the selected providers.
- Translation is performed via OpenRouter; TTS is performed via OpenAI where available.
 