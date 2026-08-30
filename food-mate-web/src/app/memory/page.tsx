import { redirect } from "next/navigation";

/**
 * Legacy memory path redirects to the login page.
 */
export default function LegacyMemoryRedirect() {
  redirect("/login");
}
