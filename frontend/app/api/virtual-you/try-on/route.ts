export const runtime = "nodejs";

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

function inferImageExtension(type: string) {
  if (type.includes("png")) {
    return "png";
  }

  if (type.includes("webp")) {
    return "webp";
  }

  return "jpg";
}

export async function POST(request: Request) {
  const tryOnServiceUrl = process.env.VIRTUAL_TRY_ON_SERVICE_URL;

  try {
    const formData = await request.formData();
    const personImage = formData.get("personImage");
    const garmentImage = formData.get("garmentImage");
    const garmentImageUrl = String(formData.get("garmentImageUrl") || "");
    const category = String(formData.get("category") || "upper_body");

    if (!(personImage instanceof File) || personImage.size === 0) {
      return errorResponse("invalid_person_image", 400);
    }

    if (!tryOnServiceUrl) {
      // 原本把人物原圖包成 mock 成功回應，畫面會假裝試穿成功但完全沒換衣服。
      // 未設定服務時必須明確失敗，讓使用者和開發者都能立刻看出設定問題。
      return errorResponse("try_on_service_unconfigured", 503);
    }

    let resolvedGarmentImage = garmentImage;

    if (!(resolvedGarmentImage instanceof File) || resolvedGarmentImage.size === 0) {
      if (!garmentImageUrl) {
        return errorResponse("invalid_garment_image", 400);
      }

      const garmentResponse = await fetch(garmentImageUrl);

      if (!garmentResponse.ok) {
        return errorResponse("garment_image_fetch_failed", 400, {
          garmentStatus: garmentResponse.status,
        });
      }

      const garmentBytes = await garmentResponse.arrayBuffer();
      const garmentType = garmentResponse.headers.get("content-type") || "image/jpeg";
      resolvedGarmentImage = new File([garmentBytes], `garment.${inferImageExtension(garmentType)}`, { type: garmentType });
    }

    if (!(resolvedGarmentImage instanceof File) || resolvedGarmentImage.size === 0) {
      return errorResponse("invalid_garment_image", 400);
    }

    const workerFormData = new FormData();
    workerFormData.append("personImage", personImage, `person.${inferImageExtension(personImage.type)}`);
    workerFormData.append(
      "garmentImage",
      resolvedGarmentImage,
      `garment.${inferImageExtension(resolvedGarmentImage.type)}`,
    );
    workerFormData.append("category", category);

    const response = await fetch(tryOnServiceUrl, {
      method: "POST",
      body: workerFormData,
    });

    if (!response.ok) {
      const responseText = await response.text().catch(() => "");
      return errorResponse("try_on_request_failed", 502, {
        tryOnStatus: response.status,
        tryOnBody: responseText.slice(0, 1200),
      });
    }

    const contentType = response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      const result = (await response.json()) as { imageBase64?: unknown; provider?: unknown };

      if (typeof result.imageBase64 !== "string") {
        return errorResponse("try_on_response_missing_image", 502);
      }

      // 舊版 Virtual You 在 provider 未設定時會用原人物圖回 mock 成功結果。
      // 不把這種假成功送回 UI，否則右側仍顯示預設人物、卻寫著已經試穿。
      if (result.provider === "mock") {
        return errorResponse("try_on_provider_mock", 503);
      }

      return Response.json({
        imageBase64: result.imageBase64,
        provider: typeof result.provider === "string" ? result.provider : "remote",
      });
    }

    const imageBytes = Buffer.from(await response.arrayBuffer());
    return Response.json({
      imageBase64: imageBytes.toString("base64"),
      provider: "remote",
    });
  } catch (error) {
    console.error("[TryOn API] Try-on route failed", error);
    return errorResponse("try_on_failed", 500, {
      message: error instanceof Error ? error.message : String(error),
    });
  }
}
