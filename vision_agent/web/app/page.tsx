import { AtlasDashboard } from "../components/atlas-dashboard";
import { getDemoState } from "../lib/atlas/demo-store";

export default function Home() {
  const initialState =
    process.env.ATLAS_SYNTHETIC_MODE === "true" || !process.env.DATABASE_URL
      ? getDemoState()
      : null;

  return <AtlasDashboard initialState={initialState} />;
}
