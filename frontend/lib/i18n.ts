import type { Lang } from "@/types";

export const LANGS: { code: Lang; label: string; bcp47: string }[] = [
  { code: "en", label: "English", bcp47: "en-IN" },
  { code: "hi", label: "हिन्दी", bcp47: "hi-IN" },
  { code: "mr", label: "मराठी", bcp47: "mr-IN" },
];

type Key =
  | "myTrips" | "takePhoto" | "retake" | "send" | "queue" | "offline" | "online" | "captured" | "queuedOffline" | "uploading"
  | "uploaded" | "processing" | "verified" | "retakeRequired" | "failed" | "ready" | "noTrips" | "tripDone" | "retry"
  | "photoHint" | "locationOn" | "locationOff" | "waitingNetwork" | "sentOk" | "needsReview" | "logout" | "listen" | "pending"
  // Spoken prompts: full instructions, not page titles.
  | "sayTakePhoto" | "sayVerified" | "sayRetake" | "sayQueued" | "sayUploading" | "sayReview" | "sayFailed"
  | "locationDenied" | "locationUnavailable" | "largePhoto" | "help"
  | "pendingLogoutTitle" | "pendingLogoutText" | "stay" | "logoutAnyway"
  // Plain-language failures (no technical messages on driver screens)
  | "errNetwork" | "errSession" | "errAlreadySent" | "errBadPhoto" | "errLinkExpired" | "errStorage" | "errGeneric";

const T: Record<Lang, Record<Key, string>> = {
  en: {
    myTrips: "My trips", takePhoto: "Take photo of receipt", retake: "Retake", send: "Send", queue: "Upload queue", offline: "No internet — photos are saved",
    online: "Online", captured: "Photo ready", queuedOffline: "Saved, will send when online", uploading: "Sending…", uploaded: "Sent", processing: "Checking…",
    verified: "Verified", retakeRequired: "Please take photo again", failed: "Could not send", ready: "Ready", noTrips: "No trips assigned",
    tripDone: "Done", retry: "Try again", photoHint: "Show the full signed and stamped receipt", locationOn: "Location saved", locationOff: "Location off",
    waitingNetwork: "Waiting for network", sentOk: "Photo sent successfully", needsReview: "Office is checking", logout: "Log out", listen: "Listen", pending: "Waiting",
    sayTakePhoto: "Take a photo of the signed receipt. Press the big camera button.", sayVerified: "Receipt accepted. Thank you.",
    sayRetake: "The photo was not clear. Please take the photo again.", sayQueued: "Photo saved on the phone. It will be sent when the network is back.",
    sayUploading: "Sending the photo.", sayReview: "Photo received. The office will check it.",
    sayFailed: "The photo could not be sent. Press try again, or call the office.",
    locationDenied: "Location is off. The photo is still saved.", locationUnavailable: "Location not found. The photo is still saved.",
    largePhoto: "Large photo. It will still be sent.", help: "Call the office",
    pendingLogoutTitle: "{n} photo(s) not sent yet", pendingLogoutText: "They stay safe on this phone and are sent after you log in again.",
    stay: "Stay", logoutAnyway: "Log out",
    errNetwork: "No network right now. The photo is saved and will be sent.", errSession: "Please log in again to send this photo.",
    errAlreadySent: "A photo for this trip was already sent.", errBadPhoto: "This photo could not be used. Please take it again.",
    errLinkExpired: "This link has expired. Ask the office for a new one.", errStorage: "Phone storage is full. Free some space and press Send again.",
    errGeneric: "Could not send. Press try again, or call the office.",
  },
  hi: {
    myTrips: "मेरी ट्रिप", takePhoto: "रसीद की फोटो लें", retake: "दोबारा लें", send: "भेजें", queue: "अपलोड कतार", offline: "इंटरनेट नहीं — फोटो सुरक्षित है",
    online: "ऑनलाइन", captured: "फोटो तैयार", queuedOffline: "सेव है, नेट आने पर भेजेंगे", uploading: "भेज रहे हैं…", uploaded: "भेज दिया", processing: "जांच हो रही है…",
    verified: "सत्यापित", retakeRequired: "कृपया फोटो फिर से लें", failed: "भेज नहीं पाए", ready: "तैयार", noTrips: "कोई ट्रिप नहीं मिली",
    tripDone: "पूरा", retry: "फिर कोशिश करें", photoHint: "हस्ताक्षर और मुहर वाली पूरी रसीद दिखाएं", locationOn: "लोकेशन सेव", locationOff: "लोकेशन बंद",
    waitingNetwork: "नेटवर्क का इंतजार", sentOk: "फोटो सफलतापूर्वक भेजी गई", needsReview: "ऑफिस जांच रहा है", logout: "लॉग आउट", listen: "सुनें", pending: "इंतजार",
    sayTakePhoto: "हस्ताक्षर वाली रसीद की फोटो लें। बड़ा कैमरा बटन दबाएं।", sayVerified: "रसीद स्वीकार हो गई। धन्यवाद।",
    sayRetake: "फोटो साफ नहीं है। कृपया फोटो फिर से लें।", sayQueued: "फोटो फोन में सेव है। नेटवर्क आने पर भेज दी जाएगी।",
    sayUploading: "फोटो भेजी जा रही है।", sayReview: "फोटो मिल गई। ऑफिस इसे जांचेगा।",
    sayFailed: "फोटो नहीं भेजी जा सकी। फिर कोशिश करें या ऑफिस को फोन करें।",
    locationDenied: "लोकेशन बंद है। फोटो फिर भी सेव है।", locationUnavailable: "लोकेशन नहीं मिली। फोटो फिर भी सेव है।",
    largePhoto: "बड़ी फोटो। फिर भी भेजी जाएगी।", help: "ऑफिस को फोन करें",
    pendingLogoutTitle: "{n} फोटो अभी नहीं भेजी गईं", pendingLogoutText: "ये फोन में सुरक्षित हैं और दोबारा लॉग इन करने पर भेजी जाएंगी।",
    stay: "रुकें", logoutAnyway: "लॉग आउट करें",
    errNetwork: "अभी नेटवर्क नहीं है। फोटो सेव है और भेज दी जाएगी।", errSession: "फोटो भेजने के लिए फिर से लॉग इन करें।",
    errAlreadySent: "इस ट्रिप की फोटो पहले ही भेजी जा चुकी है।", errBadPhoto: "यह फोटो काम नहीं आई। कृपया फिर से लें।",
    errLinkExpired: "यह लिंक बंद हो गया है। ऑफिस से नया लिंक मांगें।", errStorage: "फोन की मेमोरी भरी है। जगह खाली करके फिर भेजें।",
    errGeneric: "भेज नहीं पाए। फिर कोशिश करें या ऑफिस को फोन करें।",
  },
  mr: {
    myTrips: "माझ्या ट्रिप", takePhoto: "पावतीचा फोटो काढा", retake: "पुन्हा काढा", send: "पाठवा", queue: "अपलोड रांग", offline: "इंटरनेट नाही — फोटो सुरक्षित आहे",
    online: "ऑनलाइन", captured: "फोटो तयार", queuedOffline: "सेव्ह आहे, नेट आल्यावर पाठवू", uploading: "पाठवत आहे…", uploaded: "पाठवला", processing: "तपासणी सुरू…",
    verified: "सत्यापित", retakeRequired: "कृपया फोटो पुन्हा काढा", failed: "पाठवता आला नाही", ready: "तयार", noTrips: "कोणतीही ट्रिप नाही",
    tripDone: "पूर्ण", retry: "पुन्हा प्रयत्न करा", photoHint: "सही आणि शिक्का असलेली पूर्ण पावती दाखवा", locationOn: "लोकेशन सेव्ह", locationOff: "लोकेशन बंद",
    waitingNetwork: "नेटवर्कची प्रतीक्षा", sentOk: "फोटो यशस्वीरित्या पाठवला", needsReview: "ऑफिस तपासत आहे", logout: "लॉग आउट", listen: "ऐका", pending: "प्रतीक्षा",
    sayTakePhoto: "सही असलेल्या पावतीचा फोटो काढा. मोठे कॅमेरा बटण दाबा.", sayVerified: "पावती स्वीकारली. धन्यवाद.",
    sayRetake: "फोटो स्पष्ट नाही. कृपया फोटो पुन्हा काढा.", sayQueued: "फोटो फोनमध्ये सेव्ह आहे. नेटवर्क आल्यावर पाठवला जाईल.",
    sayUploading: "फोटो पाठवत आहे.", sayReview: "फोटो मिळाला. ऑफिस तो तपासेल.",
    sayFailed: "फोटो पाठवता आला नाही. पुन्हा प्रयत्न करा किंवा ऑफिसला फोन करा.",
    locationDenied: "लोकेशन बंद आहे. फोटो तरीही सेव्ह आहे.", locationUnavailable: "लोकेशन मिळाले नाही. फोटो तरीही सेव्ह आहे.",
    largePhoto: "मोठा फोटो. तरीही पाठवला जाईल.", help: "ऑफिसला फोन करा",
    pendingLogoutTitle: "{n} फोटो अजून पाठवले नाहीत", pendingLogoutText: "ते फोनमध्ये सुरक्षित आहेत आणि पुन्हा लॉग इन केल्यावर पाठवले जातील.",
    stay: "थांबा", logoutAnyway: "लॉग आउट करा",
    errNetwork: "आत्ता नेटवर्क नाही. फोटो सेव्ह आहे आणि पाठवला जाईल.", errSession: "फोटो पाठवण्यासाठी पुन्हा लॉग इन करा.",
    errAlreadySent: "या ट्रिपचा फोटो आधीच पाठवला आहे.", errBadPhoto: "हा फोटो वापरता आला नाही. कृपया पुन्हा काढा.",
    errLinkExpired: "ही लिंक बंद झाली आहे. ऑफिसकडून नवीन लिंक मागा.", errStorage: "फोनची मेमरी भरली आहे. जागा मोकळी करून पुन्हा पाठवा.",
    errGeneric: "पाठवता आला नाही. पुन्हा प्रयत्न करा किंवा ऑफिसला फोन करा.",
  },
};

export type I18nKey = Key;

/** Driver-facing message for a failure kind (see lib/sync driverErrorKind). */
export const ERROR_KEY: Record<string, Key> = {
  network: "errNetwork", session: "errSession", alreadySent: "errAlreadySent", badPhoto: "errBadPhoto",
  linkExpired: "errLinkExpired", storage: "errStorage", generic: "errGeneric",
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
