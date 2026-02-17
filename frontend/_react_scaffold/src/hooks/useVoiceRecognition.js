import { useState, useRef, useCallback } from "react";

export default function useVoiceRecognition({ onTranscript }) {
  const [listening, setListening] = useState(false);
  const [supported] = useState(
    typeof window !== "undefined" &&
      ("SpeechRecognition" in window || "webkitSpeechRecognition" in window)
  );
  const recognitionRef = useRef(null);

  const start = useCallback(() => {
    if (!supported) return;

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();

    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          const text = event.results[i][0].transcript.trim();
          const confidence = event.results[i][0].confidence;
          if (text && onTranscript) {
            onTranscript(text, confidence);
          }
        }
      }
    };

    recognition.onerror = (event) => {
      console.error("[STT] Error:", event.error);
      if (event.error !== "no-speech") {
        setListening(false);
      }
    };

    recognition.onend = () => {
      if (recognitionRef.current) {
        try {
          recognition.start();
        } catch {
          setListening(false);
        }
      }
    };

    recognition.start();
    recognitionRef.current = recognition;
    setListening(true);
  }, [supported, onTranscript]);

  const stop = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.onend = null;
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setListening(false);
  }, []);

  const toggle = useCallback(() => {
    if (listening) stop();
    else start();
  }, [listening, start, stop]);

  return { listening, supported, start, stop, toggle };
}
