class HaReadOnlyPanel extends HTMLElement {
  set hass(hass) {
    if (!this._initialized) {
      this._initialized = true;
      this.render();
    }
  }

  render() {
    this.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          height: 100%;
          width: 100%;
          background: var(--primary-background-color);
        }
        iframe {
          border: none;
          width: 100%;
          height: 100%;
          flex-grow: 1;
        }
      </style>
      <iframe src="/api/ha_read_only/admin"></iframe>
    `;
  }
}
customElements.define("ha-read-only-panel", HaReadOnlyPanel);