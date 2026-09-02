/**
 * The last stop before a blank page.
 *
 * React unmounts the whole tree on an uncaught render error, so a single bad
 * value anywhere becomes an empty white window with no way back and nothing to
 * report. That is the worst possible failure for a tool people leave open all
 * day, and it is worse still for a review link someone else is clicking
 * through — "it just went blank" is unactionable.
 *
 * This is not error handling. Everything recoverable is handled where it
 * happens; this catches the bugs, keeps the window showing something, and
 * offers the one action that reliably works.
 *
 * Found by exactly such a crash: the demo build answered the ⌘K search endpoint
 * with the message-search shape, the palette mapped over a missing `channels`,
 * and the app vanished. The shape is fixed — the blank page should not have
 * been possible either way.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept on the console rather than sent anywhere: this build has no
    // telemetry, and inventing a reporting endpoint here would be a surprise.
    console.error("[llack] unhandled render error", error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="crash">
        <div className="crash-plate">
          <h1>화면을 그리는 중 문제가 생겼습니다</h1>
          <p>
            이 오류는 저장된 대화에 영향을 주지 않습니다. 새로 고치면 대부분
            복구됩니다.
          </p>
          <button type="button" onClick={() => window.location.reload()}>
            새로 고침
          </button>
          {/*
            The message, verbatim and collapsed. A person reporting this needs
            something to paste, and a stack trace shown by default reads as the
            app being broken beyond use.
          */}
          <details>
            <summary>기술적 세부 정보</summary>
            <pre>{error.message}</pre>
          </details>
        </div>
      </div>
    );
  }
}
