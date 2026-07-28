import { useLocation, useNavigate } from "react-router-dom";
import { PageState } from "@/components/PageState";

export default function PermissionDenied() {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <PageState
      kind="forbidden"
      title="You don’t have access"
      description={location.state?.message || "Your role does not allow access to this page. If you think this is incorrect, ask an organisation administrator."}
      actionLabel="Return to dashboard"
      onAction={() => navigate("/dashboard", { replace: true })}
    />
  );
}
