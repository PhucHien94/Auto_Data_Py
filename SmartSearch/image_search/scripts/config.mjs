// Cấu hình duy nhất cần sửa tay. Selector lấy từ screenshot UI,
// chạy `npm run codegen` để xác nhận lại trước khi chạy full.

export const PLAYGROUND_URL =
  'https://dev-console.martonline.lotte.vn/#/search-service/playground?q=&size=100';

// 4 cơ chế đang so sánh. Thứ tự ở đây quyết định thứ tự cột trong Excel và
// dashboard — 2 biến thể Titan để cạnh nhau cho dễ đối chiếu.
// Backend còn nhận 'vector_multi' (3 ảnh đầu gallery, đã đo: HTTP 200) —
// thêm vào mảng này là nó tự chạy, không phải sửa chỗ nào khác.
// 2026-09-28: bỏ 'vector_titan' (chỉ ảnh chính), thêm 'vector_titan_multi_caption_type'
// theo yêu cầu user. Dashboard/Excel tự suy ra danh sách cơ chế từ results/, vòng
// đánh giá cũ vẫn hiện đúng nhãn Titan nhờ bảng nhãn đầy đủ trong lib/modes.json.
export const MODES = ['vector', 'vector_titan_multi', 'vector_titan_multi_caption_type', 'caption'];

// Trang có 6 <select> không id, không name, chỉ có class Angular sinh ra.
// Nên định danh từng cái bằng một option value chỉ nó mới có — bền hơn
// nth-child vì không gãy khi dev chèn thêm control hay đổi thứ tự.
export const SELECTORS = {
  // Nút camera trong ô tìm kiếm, mở modal "Tìm sản phẩm bằng hình ảnh"
  cameraButton: 'button:near(input[placeholder="Tìm kiếm"])',

  // Input file ẩn sau link "Chọn ảnh từ máy".
  // setInputFiles() bắn thẳng vào input nên không cần mô phỏng drag-drop,
  // miễn là input tồn tại trong DOM (kể cả bị ẩn).
  fileInput: 'input[type="file"]',

  // "Cơ chế ảnh:" — select duy nhất có option vector_titan
  modeSelect: 'select:has(option[value="vector_titan"])',

  // 4 select còn lại đều ảnh hưởng kết quả -> ghim cứng, xem FIXED_PARAMS
  storeSelect: 'select:has(option[value="nsg"])',
  langSelect: 'select:has(option[value="ko"])',
  searchModeSelect: 'select:has(option[value="hybrid"])',
  sortSelect: 'select:has(option[value="price_asc"])',

  // Chỉ cần khi đổi cơ chế KHÔNG tự trigger search lại.
  // Để null trước, runner sẽ báo rõ nếu cần.
  submitButton: null,
};

// Biến gây nhiễu. Không ghim thì so sánh mất giá trị:
// store khác -> tồn kho khác -> tập sản phẩm khác;
// sort khác 'relevance' -> thứ hạng do giá quyết định, mọi metric thành vô nghĩa.
// Runner set lại các giá trị này trước mỗi ảnh và ghi vào kết quả để đối chiếu.
export const FIXED_PARAMS = {
  storeSelect: 'nsg',        // Nam Sài Gòn
  langSelect: 'vi',
  sortSelect: 'relevance',
};

// Giới hạn upload của UI: PNG, JPEG, WebP, GIF — tối đa 5 MB
export const UPLOAD_LIMITS = {
  maxBytes: 5 * 1024 * 1024,
  extensions: ['.png', '.jpg', '.jpeg', '.webp', '.gif'],
};

export const PATHS = {
  manifest: 'manifest.csv',
  images: 'images',
  results: 'results',
  profile: '.auth/profile',   // profile Chromium đã đăng nhập, tạo bởi npm run auth
};

// Chạy tuần tự, có nghỉ giữa các request. Đừng tăng song song:
// sẽ làm tookMs mất ý nghĩa và dễ dính rate limit của dev console.
export const PACING = {
  delayBetweenSearchesMs: 600,
  responseTimeoutMs: 60_000,
};
