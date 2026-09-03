import React from "react";

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorCount: 0
    };
  }

  static getDerivedStateFromError(error) {
    // Apenas capturar erros específicos de DOM/insertBefore
    if (error?.name === "NotFoundError" || error?.message?.includes("insertBefore")) {
      return {
        hasError: true,
        error,
        errorCount: (prev) => (prev || 0) + 1
      };
    }
    // Deixar outros erros propagarem
    throw error;
  }

  componentDidCatch(error, errorInfo) {
    console.warn("[ErrorBoundary] DOM insertion error caught:", {
      error: error.message,
      stack: errorInfo.componentStack,
    });

    // Se o erro se repetir mais de 3 vezes, recarregar
    if (this.state.errorCount > 3) {
      console.error("[ErrorBoundary] Too many DOM errors, reloading...");
      setTimeout(() => window.location.reload(), 1000);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen bg-stone-950 text-stone-50">
          <div className="text-center p-6">
            <h2 className="text-xl font-bold mb-2">Erro de renderização</h2>
            <p className="text-stone-400 text-sm mb-4">
              Ocorreu um problema ao atualizar a página. Tentando recuperar...
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
              }}
              className="px-4 py-2 bg-orange-600 text-white rounded-lg text-sm hover:bg-orange-700 transition"
            >
              Tentar novamente
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
