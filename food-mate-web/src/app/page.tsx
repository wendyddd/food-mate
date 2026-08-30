import { redirect } from "next/navigation";

/**
 * Root path redirects to the login page.
 */
export default function RootPage() {
  redirect("/login");
}
