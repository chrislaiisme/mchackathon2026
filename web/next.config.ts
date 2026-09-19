import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 這個 repo 的上層（家目錄）有一個 package-lock.json，Next.js 會因此把工作區根目錄
  // 推斷到那裡，連帶不讀 web/.env.local —— 症狀是 NEXT_PUBLIC_* 全部拿到 undefined，
  // 商品圖片打到錯的埠而 404。釘死根目錄就不會再推斷錯。
  turbopack: { root: path.resolve(__dirname) },
};

export default nextConfig;
