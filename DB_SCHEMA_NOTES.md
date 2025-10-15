### JSON Field Notes

This document provides a brief overview of the JSON fields in the database schema.

*   **`pages.dimensions`**: This JSON field stores the width and height of the page image. It is a JSON object with the following keys:
    *   `width`: The width of the page image in pixels.
    *   `height`: The height of the page image in pixels.

*   **`words.geometry`**: This JSON field stores the bounding box of the word. It is a JSON array of four floating-point numbers representing the `[x_min, y_min, x_max, y_max]` coordinates of the bounding box, normalized to the dimensions of the page image.
