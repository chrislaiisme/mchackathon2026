export const runtime = "nodejs";

const isDevelopment = process.env.NODE_ENV !== "production";
const DEFAULT_EXTRACTION_SERVICE_URL = "http://127.0.0.1:8081/extract";

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
  const extractionServiceUrl = process.env.PERSON_EXTRACTION_SERVICE_URL || DEFAULT_EXTRACTION_SERVICE_URL;

  console.log("[CreateYou API] Request received");
  console.log("[CreateYou API] Extraction service:", extractionServiceUrl);

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

    const baseImageFormData = new FormData();
    baseImageFormData.append("image", image, image.name || "create-you-source.png");

    console.log("[CreateYou API] Image received", {
      name: image.name,
      type: image.type,
      size: image.size,
    });

    console.log("[CreateYou API] Calling extraction service");
    const response = await fetch(extractionServiceUrl, {
      method: "POST",
      body: baseImageFormData,
    });

    console.log("[CreateYou API] Extraction service status:", response.status);

    if (!response.ok) {
      const responseText = await response.text().catch(() => "");
      let parsedBody: unknown = null;

      try {
        parsedBody = responseText ? JSON.parse(responseText) : null;
      } catch {
        parsedBody = null;
      }

      console.error("[CreateYou API] Extraction service failed", {
        url: extractionServiceUrl,
        status: response.status,
        body: responseText.slice(0, 1200),
        parsedBody,
      });
      return errorResponse("extraction_request_failed", 502, {
        extractionStatus: response.status,
        extractionUrl: extractionServiceUrl,
        extractionBody: responseText.slice(0, 1200),
        extractionParsedBody: parsedBody,
        hint:
          response.status === 422
            ? "FastAPI rejected the multipart form. Verify PERSON_EXTRACTION_SERVICE_URL points to /extract and the endpoint expects field name image."
            : undefined,
      });
    }

    const contentType = response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      const result = (await response.json()) as { imageBase64?: unknown };
      const imageBase64 = result.imageBase64;

      if (typeof imageBase64 !== "string") {
        console.error("[CreateYou API] Extraction response missing image data");
        return errorResponse("extraction_response_missing_image", 502);
      }

      return Response.json({ imageBase64 });
    }

    const imageBytes = Buffer.from(await response.arrayBuffer());
    const imageBase64 = imageBytes.toString("base64");

    console.log("[CreateYou API] Extraction response received", {
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
