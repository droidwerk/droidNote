import { Card } from "../shared/ui/primitives";
import { PrivacyPolicy } from "../shared/ui/PrivacyPolicy";

export function PrivacyPage() {
  return (
    <Card className="privacy-card">
      <PrivacyPolicy />
    </Card>
  );
}
