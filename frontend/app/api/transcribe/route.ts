export const runtime = "nodejs";

const OPENAI_TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions";
const TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe";

export async function POST(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY;

  if (!apiKey) {
    return Response.json({ error: "missing_api_key" }, { status: 503 });
  }

  try {
    const formData = await request.formData();
    const audio = formData.get("audio");

    if (!(audio instanceof File) || audio.size === 0) {
      return Response.json({ error: "invalid_audio" }, { status: 400 });
    }

    const openAiFormData = new FormData();
    openAiFormData.append("file", audio, audio.name || "intentweave-voice.webm");
    openAiFormData.append("model", TRANSCRIPTION_MODEL);

    const response = await fetch(OPENAI_TRANSCRIPTION_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
      },
      body: openAiFormData,
    });

    if (!response.ok) {
      return Response.json({ error: "transcription_failed" }, { status: 502 });
    }

    const result = (await response.json()) as { text?: unknown };
    const text = typeof result.text === "string" ? result.text.trim() : "";

    if (!text) {
      return Response.json({ error: "transcription_failed" }, { status: 502 });
    }

    return Response.json({ text });
  } catch {
    return Response.json({ error: "transcription_failed" }, { status: 500 });
  }
}
