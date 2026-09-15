import "./weave-spinner.css";

export function WeaveSpinner() {
  return <div className="weave-spinner" aria-hidden="true">
    <div className="weave-spinner__stage">
      <i className="weave-spinner__thread weave-spinner__thread--one" />
      <i className="weave-spinner__thread weave-spinner__thread--two" />
      <i className="weave-spinner__thread weave-spinner__thread--three" />
      <i className="weave-spinner__thread weave-spinner__thread--four" />
      <span className="weave-spinner__node" />
    </div>
  </div>;
}
