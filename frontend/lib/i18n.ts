import type { Lang } from "@/types";

export const LANGS: { code: Lang; label: string; bcp47: string }[] = [
  { code: "en", label: "English", bcp47: "en-IN" },
  { code: "hi", label: "हिन्दी", bcp47: "hi-IN" },
  { code: "mr", label: "मराठी", bcp47: "mr-IN" },
];

type Key =
  | "myTrips" | "takePhoto" | "retake" | "send" | "queue" | "offline" | "online" | "captured" | "queuedOffline" | "uploading"
  | "uploaded" | "processing" | "verified" | "retakeRequired" | "failed" | "ready" | "noTrips" | "tripDone" | "retry"
  | "photoHint" | "locationOn" | "locationOff" | "waitingNetwork" | "sentOk" | "needsReview" | "logout" | "listen" | "pending";

const T: Record<Lang, Record<Key, string>> = {
  en: {
    myTrips: "My trips", takePhoto: "Take photo of receipt", retake: "Retake", send: "Send", queue: "Upload queue", offline: "No internet — photos are saved",
    online: "Online", captured: "Photo ready", queuedOffline: "Saved, will send when online", uploading: "Sending…", uploaded: "Sent", processing: "Checking…",
    verified: "Verified", retakeRequired: "Please take photo again", failed: "Could not send", ready: "Ready", noTrips: "No trips assigned",
    tripDone: "Done", retry: "Try again", photoHint: "Show the full signed and stamped receipt", locationOn: "Location saved", locationOff: "Location off",
    waitingNetwork: "Waiting for network", sentOk: "Photo sent successfully", needsReview: "Office is checking", logout: "Log out", listen: "Listen", pending: "Waiting",
  },
  hi: {
    myTrips: "मेरी ट्रिप", takePhoto: "रसीद की फोटो लें", retake: "दोबारा लें", send: "भेजें", queue: "अपलोड कतार", offline: "इंटरनेट नहीं — फोटो सुरक्षित है",
    online: "ऑनलाइन", captured: "फोटो तैयार", queuedOffline: "सेव है, नेट आने पर भेजेंगे", uploading: "भेज रहे हैं…", uploaded: "भेज दिया", processing: "जांच हो रही है…",
    verified: "सत्यापित", retakeRequired: "कृपया फोटो फिर से लें", failed: "भेज नहीं पाए", ready: "तैयार", noTrips: "कोई ट्रिप नहीं मिली",
    tripDone: "पूरा", retry: "फिर कोशिश करें", photoHint: "हस्ताक्षर और मुहर वाली पूरी रसीद दिखाएं", locationOn: "लोकेशन सेव", locationOff: "लोकेशन बंद",
    waitingNetwork: "नेटवर्क का इंतजार", sentOk: "फोटो सफलतापूर्वक भेजी गई", needsReview: "ऑफिस जांच रहा है", logout: "लॉग आउट", listen: "सुनें", pending: "इंतजार",
  },
  mr: {
    myTrips: "माझ्या ट्रिप", takePhoto: "पावतीचा फोटो काढा", retake: "पुन्हा काढा", send: "पाठवा", queue: "अपलोड रांग", offline: "इंटरनेट नाही — फोटो सुरक्षित आहे",
    online: "ऑनलाइन", captured: "फोटो तयार", queuedOffline: "सेव्ह आहे, नेट आल्यावर पाठवू", uploading: "पाठवत आहे…", uploaded: "पाठवला", processing: "तपासणी सुरू…",
    verified: "सत्यापित", retakeRequired: "कृपया फोटो पुन्हा काढा", failed: "पाठवता आला नाही", ready: "तयार", noTrips: "कोणतीही ट्रिप नाही",
    tripDone: "पूर्ण", retry: "पुन्हा प्रयत्न करा", photoHint: "सही आणि शिक्का असलेली पूर्ण पावती दाखवा", locationOn: "लोकेशन सेव्ह", locationOff: "लोकेशन बंद",
    waitingNetwork: "नेटवर्कची प्रतीक्षा", sentOk: "फोटो यशस्वीरित्या पाठवला", needsReview: "ऑफिस तपासत आहे", logout: "लॉग आउट", listen: "ऐका", pending: "प्रतीक्षा",
  },
};

export const t = (lang: Lang, key: Key) => T[lang]?.[key] ?? T.en[key];

export function speechSupported() {
  return typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
}

/** Speaks in the chosen language where the browser/voice supports it. Returns false so the UI can show the text fallback. */
export function speak(text: string, lang: Lang): boolean {
  if (!speechSupported()) return false;
  try {
    const bcp = LANGS.find((l) => l.code === lang)!.bcp47;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = bcp;
    const voice = window.speechSynthesis.getVoices().find((v) => v.lang.toLowerCase().startsWith(bcp.slice(0, 2)));
    if (voice) u.voice = voice;
    else if (lang !== "en") return false; // no Hindi/Marathi voice installed: fall back to on-screen text
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
    return true;
  } catch { return false; }
}
