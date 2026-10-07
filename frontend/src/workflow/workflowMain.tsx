import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { WorkflowInterface } from "./WorkflowInterface";
import "../index.css";
import "../createColors.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <WorkflowInterface />
  </StrictMode>
);
