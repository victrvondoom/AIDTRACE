export const VOICE_LANGUAGES = [
  { code: "auto", label: "Auto-detect", speechLocale: "" },
  { code: "en", label: "English", speechLocale: "en-IN" },
  { code: "hi", label: "Hindi", speechLocale: "hi-IN" },
  { code: "bn", label: "Bengali", speechLocale: "bn-IN" },
  { code: "te", label: "Telugu", speechLocale: "te-IN" },
  { code: "mr", label: "Marathi", speechLocale: "mr-IN" },
  { code: "ta", label: "Tamil", speechLocale: "ta-IN" },
  { code: "ur", label: "Urdu", speechLocale: "ur-IN" },
  { code: "gu", label: "Gujarati", speechLocale: "gu-IN" },
  { code: "kn", label: "Kannada", speechLocale: "kn-IN" },
  { code: "ml", label: "Malayalam", speechLocale: "ml-IN" },
  { code: "pa", label: "Punjabi", speechLocale: "pa-IN" },
  { code: "or", label: "Odia", speechLocale: "or-IN" },
  { code: "es", label: "Spanish", speechLocale: "es-ES" },
  { code: "fr", label: "French", speechLocale: "fr-FR" },
  { code: "pt", label: "Portuguese", speechLocale: "pt-BR" },
  { code: "ar", label: "Arabic", speechLocale: "ar-SA" },
  { code: "zh", label: "Chinese", speechLocale: "zh-CN" },
  { code: "ja", label: "Japanese", speechLocale: "ja-JP" },
] as const;

export type VoiceLanguage = (typeof VOICE_LANGUAGES)[number]["code"];
