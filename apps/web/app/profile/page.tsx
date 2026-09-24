import { redirect } from "next/navigation";

// Profile setup moved to the landing page.
export default function ProfileRedirect() {
  redirect("/");
}
