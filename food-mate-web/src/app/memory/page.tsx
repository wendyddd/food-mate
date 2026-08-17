import { redirect } from "next/navigation";

/**
 * 旧版记忆页路径重定向到登录页。
 */
export default function LegacyMemoryRedirect() {
  redirect("/login");
}
