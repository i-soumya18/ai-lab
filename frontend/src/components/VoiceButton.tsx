"use client";

import { useState } from "react";

interface Props {
  onTranscript: (text: string) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function VoiceButton({ onTranscript }: Props) {
  const [recording, setRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      const chunks: Blob[] = [];

      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: "audio/webm" });
        await transcribe(blob);
      };

      recorder.start();
      setMediaRecorder(recorder);
      setRecording(true);
    } catch {
      alert("Microphone access denied");
    }
  };

  const stopRecording = () => {
    mediaRecorder?.stop();
    setRecording(false);
    setMediaRecorder(null);
  };

  const transcribe = async (blob: Blob) => {
    const form = new FormData();
    form.append("file", blob, "recording.webm");
    try {
      const res = await fetch(`${API_BASE}/api/v1/voice/transcribe`, {
        method: "POST",
        body: form,
      });
      const json = await res.json();
      const transcript = json?.data?.transcript ?? "";
      if (transcript) onTranscript(transcript);
    } catch {
      console.error("Transcription failed");
    }
  };

  return (
    <button
      type="button"
      onClick={recording ? stopRecording : startRecording}
      title={recording ? "Stop recording" : "Start voice input"}
      className={`
        flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center
        transition-colors duration-200
        ${
          recording
            ? "bg-red-600 hover:bg-red-700 animate-pulse"
            : "bg-ailab-surface border border-ailab-border hover:bg-ailab-border"
        }
      `}
    >
      <svg
        className="w-5 h-5 text-ailab-text"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        {recording ? (
          <rect x="6" y="6" width="12" height="12" rx="2" strokeWidth={2} />
        ) : (
          <>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"
            />
          </>
        )}
      </svg>
    </button>
  );
}
