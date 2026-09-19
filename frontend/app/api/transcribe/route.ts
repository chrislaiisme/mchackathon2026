export const runtime = "nodejs";

const OPENAI_TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions";
const TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe";
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
  | "missing_api_key"
  | "invalid_audio"
  | "unsupported_audio"
  | "openai_rate_limited"
  | "openai_quota_exceeded"
  | "openai_request_failed"
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

function isQuotaError(status: number, body: string) {
  const lowerBody = body.toLowerCase();

  return (
    status === 429 &&
    (lowerBody.includes("insufficient_quota") || lowerBody.includes("quota") || lowerBody.includes("credit"))
  );
}

export async function POST(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY;

  console.log("[Voice API] Request received");
  console.log("[Voice API] OPENAI_API_KEY exists:", Boolean(apiKey));

  if (!apiKey) {
    console.error("[Voice API] Missing OPENAI_API_KEY");
    return jsonError("missing_api_key", 503, "OPENAI_API_KEY is not configured on the server.");
  }

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

    const openAiFormData = new FormData();
    openAiFormData.append("file", audio, audio.name || "intentweave-voice.webm");
    openAiFormData.append("model", TRANSCRIPTION_MODEL);

    console.log("[Voice API] Calling OpenAI:", {
      endpoint: OPENAI_TRANSCRIPTION_URL,
      model: TRANSCRIPTION_MODEL,
    });

    const response = await fetch(OPENAI_TRANSCRIPTION_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
      },
      body: openAiFormData,
    });

    console.log("[Voice API] OpenAI status:", response.status);

    if (!response.ok) {
      const responseBody = await response.text().catch(() => "");

      console.error("[Voice API] OpenAI transcription failed:", {
        status: response.status,
        body: responseBody,
      });

      if (isQuotaError(response.status, responseBody)) {
        return jsonError("openai_quota_exceeded", 429, "OpenAI quota or credits are exhausted.");
      }

      if (response.status === 429) {
        return jsonError("openai_rate_limited", 429, "OpenAI rate limit was reached.");
      }

      return jsonError("openai_request_failed", 502, `OpenAI transcription request failed with status ${response.status}.`);
    }

    const result = (await response.json()) as { text?: unknown };
    const text = typeof result.text === "string" ? result.text.trim() : "";

    if (!text) {
      console.error("[Voice API] OpenAI response did not include transcription text");
      return jsonError("transcription_empty", 502, "OpenAI returned an empty transcription.");
    }

    console.log("[Voice API] Transcription received:", {
      textLength: text.length,
    });

    return Response.json({ text });
  } catch (error) {
    console.error("[Voice API] Transcription route error:", error);
    return jsonError("transcription_failed", 500, "Unexpected transcription route error.");
  }
}
