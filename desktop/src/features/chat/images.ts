import type { ChatImageDraft } from "../../shared/api/types";

export const IMAGE_ACCEPT = ".png,.jpg,.jpeg,.webp,.gif,.bmp";
export const MAX_IMAGES = 3;
const MAX_SIDE = 1600;

export function isImageFile(file: File): boolean {
  return file.type.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name);
}

/** Reduz a foto do quadro para o modelo (lado maior 1600 px, JPEG) e devolve o base64 sem prefixo. */
export async function prepareImage(file: File): Promise<ChatImageDraft> {
  const bitmap = await loadBitmap(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("canvas");
  // Fundo branco: PNG transparente vira imagem legível no JPEG.
  context.fillStyle = "#fff";
  context.fillRect(0, 0, width, height);
  context.drawImage(bitmap, 0, 0, width, height);
  if ("close" in bitmap) bitmap.close();
  const preview = canvas.toDataURL("image/jpeg", 0.85);
  return { name: file.name, mime: "image/jpeg", data: preview.slice(preview.indexOf(",") + 1), preview };
}

async function loadBitmap(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if ("createImageBitmap" in window) {
    try {
      return await createImageBitmap(file);
    } catch {
      /* formato que o bitmap não lê: cai no <img> */
    }
  }
  const url = URL.createObjectURL(file);
  try {
    return await new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("image"));
      image.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}
