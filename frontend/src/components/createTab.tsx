import { Wrench, Puzzle, Brain, Database, Workflow } from "lucide-react";
import { useCallback } from "react";
import { Button } from "./ui/button";

export function CreateTab() {
  const openPage = useCallback((page: string) => {
    const base = window.location.origin;
    window.open(`${base}/${page}`, "_blank", "noopener,noreferrer");
  }, []);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      <div className="text-xs font-medium text-app-text-secondary">
        Crear herramientas, skills, agentes, workflows y RAG
      </div>
      <p className="text-[11px] text-app-text-secondary">
        Esta funcionalidad está disponible en modo dev. Selecciona qué tipo de elemento crear y sigue las instrucciones.
      </p>
      <div className="space-y-2">
        <Button className="w-full justify-start gap-2" variant="outline" onClick={() => openPage("tool.html")}>
          <Wrench size={14} />
          Crear Tool
        </Button>
        <Button className="w-full justify-start gap-2" variant="outline" onClick={() => openPage("skill.html")}>
          <Puzzle size={14} />
          Crear Skill
        </Button>
        <Button className="w-full justify-start gap-2" variant="outline" onClick={() => openPage("agent.html")}>
          <Brain size={14} />
          Crear Agente
        </Button>
        <Button className="w-full justify-start gap-2" variant="outline" onClick={() => openPage("workflow.html")}>
          <Workflow size={14} />
          Crear Workflow
        </Button>
        <Button className="w-full justify-start gap-2" variant="outline" onClick={() => openPage("rag.html")}>
          <Database size={14} />
          Gestionar RAG
        </Button>
      </div>
    </div>
  );
}

export default CreateTab;