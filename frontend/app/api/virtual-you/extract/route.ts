export const runtime = "nodejs";

const OPENAI_IMAGE_EDIT_URL = "https://api.openai.com/v1/images/edits";
const IMAGE_EDIT_MODEL = "gpt-image-1";
const isDevelopment = process.env.NODE_ENV !== "production";

function errorResponse(error: string, status: number, details?: Record<string, unknown>) {
  return Response.json(
    {
      error,
      ...(isDevelopment && details ? { details } : {}),
    },
    { status },
  );
}

export async function POST(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY;

  console.log("[CreateYou API] Request received");
  console.log("[CreateYou API] OPENAI_API_KEY exists:", Boolean(apiKey));

  if (!apiKey) {
    console.error("[CreateYou API] Missing OPENAI_API_KEY");
    return errorResponse("missing_api_key", 503);
  }

  try {
    const formData = await request.formData();
    const image = formData.get("image");

    if (!(image instanceof File) || image.size === 0) {
      console.error("[CreateYou API] Invalid image payload", {
        hasImage: Boolean(image),
        valueType: image?.constructor?.name,
      });
      return errorResponse("invalid_image", 400);
    }

    console.log("[CreateYou API] Image received", {
      name: image.name,
      type: image.type,
      size: image.size,
    });

    const extractionFormData = new FormData();
    extractionFormData.append("model", IMAGE_EDIT_MODEL);
    extractionFormData.append("image", image, image.name || "create-you-source.png");
    extractionFormData.append("background", "transparent");
    extractionFormData.append("output_format", "png");
    extractionFormData.append("size", "1024x1536");
    extractionFormData.append(
      "prompt",
      [
        "Detect the primary human subject in this photo.",
        "Remove all scenery, furniture, sky, ground, buildings, and other background objects.",
        "Return only the person on a transparent background as a realistic fashion-editorial cutout.",
        "Preserve the person's face, hair, body proportions, pose, limbs, shoes, clothing silhouette, and attached accessories.",
        "Do not add a background, caption, frame, mannequin, cartoon style, or 3D avatar styling.",
      ].join(" "),
    );

    console.log("[CreateYou API] Calling OpenAI", {
      endpoint: OPENAI_IMAGE_EDIT_URL,
      model: IMAGE_EDIT_MODEL,
    });

    const response = await fetch(OPENAI_IMAGE_EDIT_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
      },
      body: extractionFormData,
    });

    console.log("[CreateYou API] OpenAI status:", response.status);

    if (!response.ok) {
      const responseText = await response.text().catch(() => "");
      console.error("[CreateYou API] OpenAI request failed", {
        status: response.status,
        body: responseText.slice(0, 1200),
      });
      return errorResponse("openai_request_failed", 502, {
        openaiStatus: response.status,
        openaiBody: responseText.slice(0, 1200),
      });
    }

    const result = (await response.json()) as { data?: Array<{ b64_json?: unknown }> };
    const imageBase64 = result.data?.find((item) => typeof item.b64_json === "string")?.b64_json;

    if (typeof imageBase64 !== "string") {
      console.error("[CreateYou API] OpenAI response missing image data", {
        hasData: Array.isArray(result.data),
        dataLength: result.data?.length || 0,
      });
      return errorResponse("openai_response_missing_image", 502, {
        hasData: Array.isArray(result.data),
        dataLength: result.data?.length || 0,
      });
    }

    console.log("[CreateYou API] OpenAI response received", {
      imageBase64Length: imageBase64.length,
    });

    return Response.json({ imageBase64 });
  } catch (error) {
    console.error("[CreateYou API] Image extraction route failed", error);
    return errorResponse("background_removal_failed", 500, {
      message: error instanceof Error ? error.message : String(error),
    });
  }
}
