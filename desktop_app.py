from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from transwell_counter import CounterParams, CountResult, count_cells, load_rgb_image


SUPPORTED_TYPES = [
    ("Image files", "*.tif *.tiff *.png *.jpg *.jpeg *.bmp"),
    ("TIFF files", "*.tif *.tiff"),
    ("PNG files", "*.png"),
    ("JPEG files", "*.jpg *.jpeg"),
    ("BMP files", "*.bmp"),
    ("All files", "*.*"),
]


class StainSpotDesktop(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("StainSpot Counter")
        self.geometry("1180x760")
        self.minsize(980, 640)

        self.image_path: Path | None = None
        self.original_image: Image.Image | None = None
        self.result: CountResult | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self._build_ui()
        self.after(100, self._poll_worker)

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self, padding=12)
        sidebar.grid(row=0, column=0, sticky="ns")

        ttk.Label(sidebar, text="StainSpot Counter", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 10))
        ttk.Button(sidebar, text="Open image", command=self.open_image).pack(fill="x", pady=(0, 8))
        ttk.Button(sidebar, text="Analyze", command=self.start_analysis).pack(fill="x", pady=(0, 16))

        self.status_var = tk.StringVar(value="Open an image to start.")
        ttk.Label(sidebar, textvariable=self.status_var, wraplength=260).pack(anchor="w", pady=(0, 12))

        params_frame = ttk.LabelFrame(sidebar, text="Detection settings", padding=10)
        params_frame.pack(fill="x", pady=(0, 12))

        self.sensitivity = self._add_scale(params_frame, "Sensitivity", 0.0, 1.0, 0.50, 0.01)
        self.min_area = self._add_int_scale(params_frame, "Minimum area", 10, 500, 70, 5)
        self.max_area = self._add_int_scale(params_frame, "Maximum area", 300, 5000, 1800, 50)
        self.min_solidity = self._add_scale(params_frame, "Minimum solidity", 0.10, 1.0, 0.48, 0.01)
        self.min_center_score = self._add_scale(params_frame, "Minimum center stain", 0.0, 1.0, 0.22, 0.01)
        self.max_hole_ratio = self._add_scale(params_frame, "Maximum hollow ratio", 0.0, 0.9, 0.32, 0.01)
        self.split_distance = self._add_int_scale(params_frame, "Splitting distance", 3, 35, 11, 1)

        self.show_numbers = tk.BooleanVar(value=False)
        ttk.Checkbutton(sidebar, text="Show IDs", variable=self.show_numbers).pack(anchor="w", pady=(0, 4))
        self.exclude_border = tk.BooleanVar(value=False)
        ttk.Checkbutton(sidebar, text="Exclude border objects", variable=self.exclude_border).pack(anchor="w", pady=(0, 12))

        ttk.Button(sidebar, text="Save annotated image", command=self.save_annotated).pack(fill="x", pady=(0, 6))
        ttk.Button(sidebar, text="Save mask", command=self.save_mask).pack(fill="x", pady=(0, 6))
        ttk.Button(sidebar, text="Save stain score", command=self.save_score).pack(fill="x", pady=(0, 6))

        main = ttk.Frame(self, padding=(0, 12, 12, 12))
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        metrics = ttk.Frame(main)
        metrics.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.count_var = tk.StringVar(value="Detected objects: -")
        self.threshold_var = tk.StringVar(value="Threshold: -")
        self.image_var = tk.StringVar(value="Image: -")
        ttk.Label(metrics, textvariable=self.count_var, font=("Segoe UI", 13, "bold")).pack(side="left", padx=(0, 24))
        ttk.Label(metrics, textvariable=self.threshold_var).pack(side="left", padx=(0, 24))
        ttk.Label(metrics, textvariable=self.image_var).pack(side="left")

        preview_frame = ttk.Frame(main)
        preview_frame.grid(row=1, column=0, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self.preview_label = ttk.Label(preview_frame, anchor="center", text="No image loaded")
        self.preview_label.grid(row=0, column=0, sticky="nsew")
        self.preview_label.bind("<Configure>", lambda _event: self.update_preview())

    def _add_scale(self, parent: ttk.Frame, label: str, low: float, high: float, value: float, step: float) -> tk.DoubleVar:
        variable = tk.DoubleVar(value=value)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 8))
        value_label = ttk.Label(row, text=f"{label}: {value:.2f}")
        value_label.pack(anchor="w")

        def update(_val: str) -> None:
            rounded = round(variable.get() / step) * step
            variable.set(round(rounded, 4))
            value_label.configure(text=f"{label}: {variable.get():.2f}")

        ttk.Scale(row, from_=low, to=high, variable=variable, command=update).pack(fill="x")
        return variable

    def _add_int_scale(self, parent: ttk.Frame, label: str, low: int, high: int, value: int, step: int) -> tk.IntVar:
        variable = tk.IntVar(value=value)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 8))
        value_label = ttk.Label(row, text=f"{label}: {value}")
        value_label.pack(anchor="w")

        def update(_val: str) -> None:
            rounded = int(round(variable.get() / step) * step)
            variable.set(max(low, min(high, rounded)))
            value_label.configure(text=f"{label}: {variable.get()}")

        ttk.Scale(row, from_=low, to=high, variable=variable, command=update).pack(fill="x")
        return variable

    def current_params(self) -> CounterParams:
        return CounterParams(
            sensitivity=float(self.sensitivity.get()),
            min_area=int(self.min_area.get()),
            max_area=int(self.max_area.get()),
            min_solidity=float(self.min_solidity.get()),
            max_hole_ratio=float(self.max_hole_ratio.get()),
            min_center_score=float(self.min_center_score.get()),
            split_distance=int(self.split_distance.get()),
            exclude_border=bool(self.exclude_border.get()),
        )

    def open_image(self) -> None:
        selected = filedialog.askopenfilename(title="Open image", filetypes=SUPPORTED_TYPES)
        if not selected:
            return
        try:
            self.image_path = Path(selected)
            self.original_image = load_rgb_image(self.image_path)
            self.result = None
            self.status_var.set("Image loaded. Click Analyze.")
            self.image_var.set(f"Image: {self.image_path.name} ({self.original_image.size[0]} x {self.original_image.size[1]})")
            self.count_var.set("Detected objects: -")
            self.threshold_var.set("Threshold: -")
            self.update_preview()
        except Exception as exc:
            messagebox.showerror("Open image failed", str(exc))

    def start_analysis(self) -> None:
        if self.original_image is None:
            messagebox.showinfo("No image", "Open an image first.")
            return
        self.status_var.set("Analyzing...")
        params = self.current_params()
        image = self.original_image.copy()
        show_numbers = bool(self.show_numbers.get())
        threading.Thread(target=self._analyze_worker, args=(image, params, show_numbers), daemon=True).start()

    def _analyze_worker(self, image: Image.Image, params: CounterParams, show_numbers: bool) -> None:
        try:
            result = count_cells(image, params, show_numbers=show_numbers)
            self.worker_queue.put(("result", result))
        except Exception as exc:
            self.worker_queue.put(("error", exc))

    def _poll_worker(self) -> None:
        try:
            while True:
                kind, payload = self.worker_queue.get_nowait()
                if kind == "result":
                    self.result = payload  # type: ignore[assignment]
                    self.status_var.set("Analysis complete.")
                    self.count_var.set(f"Detected objects: {self.result.count}")
                    self.threshold_var.set(f"Threshold: {self.result.threshold:.3f}")
                    self.update_preview()
                elif kind == "error":
                    self.status_var.set("Analysis failed.")
                    messagebox.showerror("Analysis failed", str(payload))
        except queue.Empty:
            pass
        self.after(100, self._poll_worker)

    def update_preview(self) -> None:
        image = self.result.annotated_image if self.result is not None else self.original_image
        if image is None:
            return
        width = max(100, self.preview_label.winfo_width())
        height = max(100, self.preview_label.winfo_height())
        preview = image.copy()
        preview.thumbnail((width, height), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self.preview_photo, text="")

    def _save_image(self, image: Image.Image | None, suffix: str) -> None:
        if image is None:
            messagebox.showinfo("No result", "Analyze an image first.")
            return
        default_name = "stainspot_result.png"
        if self.image_path is not None:
            default_name = f"{self.image_path.stem}_{suffix}.png"
        selected = filedialog.asksaveasfilename(
            title="Save image",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
        )
        if selected:
            image.save(selected)
            self.status_var.set(f"Saved {Path(selected).name}.")

    def save_annotated(self) -> None:
        self._save_image(self.result.annotated_image if self.result else None, "annotated")

    def save_mask(self) -> None:
        self._save_image(self.result.mask_image if self.result else None, "mask")

    def save_score(self) -> None:
        self._save_image(self.result.score_image if self.result else None, "score")


def main() -> None:
    app = StainSpotDesktop()
    app.mainloop()


if __name__ == "__main__":
    main()
