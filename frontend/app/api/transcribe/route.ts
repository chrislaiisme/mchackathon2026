export const runtime = "nodejs";

const WHISPER_API_URL = process.env.WHISPER_API_URL || "http://127.0.0.1:9000/transcribe";
const SUPPORTED_AUDIO_TYPES = new Set([
  "audio/flac",
  "audio/mp3",
  "audio/mp4",
  "audio/mpeg",
  "audio/mpga",
  "audio/m4a",
  "audio/ogg",
  "audio/wav",
  "audio/webm",
  "audio/x-wav",
]);

type TranscriptionError =
  | "invalid_audio"
  | "unsupported_audio"
  | "whisper_unavailable"
  | "whisper_request_failed"
  | "transcription_empty"
  | "transcription_failed";

function jsonError(error: TranscriptionError, status: number, details?: string) {
  return Response.json(
    {
      error,
      ...(process.env.NODE_ENV !== "production" && details ? { details } : {}),
    },
    { status },
  );
}

function getBaseAudioType(type: string) {
  return type.split(";")[0]?.trim().toLowerCase() || "";
}

export async function POST(request: Request) {
  console.log("[Voice API] Request received");

  try {
    const formData = await request.formData();
    const audio = formData.get("audio");

    if (!(audio instanceof File) || audio.size === 0) {
      console.error("[Voice API] Invalid or empty audio upload");
      return jsonError("invalid_audio", 400, "No non-empty audio file was provided.");
    }

    const audioType = getBaseAudioType(audio.type);

    console.log("[Voice API] Audio received:", {
      name: audio.name,
      type: audio.type || "(empty)",
      size: audio.size,
    });

    if (audioType && !SUPPORTED_AUDIO_TYPES.has(audioType)) {
      console.error("[Voice API] Unsupported audio type:", audio.type);
      return jsonError("unsupported_audio", 415, `Unsupported audio type: ${audio.type}`);
    }

    const whisperFormData = new FormData();
    whisperFormData.append("audio", audio, audio.name || "intentweave-voice.webm");

    console.log("[Voice API] Calling local Whisper:", {
      endpoint: WHISPER_API_URL,
    });

    const response = await fetch(WHISPER_API_URL, {
      method: "POST",
      body: whisperFormData,
    });

    console.log("[Voice API] Whisper status:", response.status);

    if (!response.ok) {
      const responseBody = await response.text().catch(() => "");

      console.error("[Voice API] Whisper transcription failed:", {
        status: response.status,
        body: responseBody,
      });
      return jsonError("whisper_request_failed", 502, `Whisper request failed with status ${response.status}.`);
    }

    const result = (await response.json()) as { text?: unknown };
    const text = typeof result.text === "string" ? result.text.trim() : "";

    if (!text) {
      console.error("[Voice API] Whisper response did not include transcription text");
      return jsonError("transcription_empty", 502, "Whisper returned an empty transcription.");
    }

    console.log("[Voice API] Transcription received:", {
      textLength: text.length,
    });

    return Response.json({ text });
  } catch (error) {
    console.error("[Voice API] Transcription route error:", error);
    return jsonError("whisper_unavailable", 503, "The local Whisper service is unavailable.");
  }
}
