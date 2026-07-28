import { useNavigate } from "react-router-dom";
import { PageState } from "@/components/PageState";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <PageState
      title="Page not found"
      description="The address may be incorrect, or the page may have moved."
      actionLabel="Go to FleetFlow home"
      onAction={() => navigate("/", { replace: true })}
    />
  );
}
