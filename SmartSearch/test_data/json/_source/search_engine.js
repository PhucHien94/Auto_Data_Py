// Smart search/autocomplete simulation engine for the NSG test-data artifact.
// Pure functions, no DOM — loadable both under Node (for generation/validation)
// and in the browser artifact (for live ad-hoc queries).
//
// Priority order per spec: Tên sản phẩm chính xác > Từ khóa trong Description >
// Từ đồng nghĩa/ngữ cảnh sử dụng.

(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SearchEngine = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Glossaries — curated against NSG's real catalog (grocery/convenience
  // mart: THỰC PHẨM KHÔ, HÀNG PHI THỰC PHẨM, THỰC PHẨM TƯƠI SỐNG, THỜI
  // TRANG, BỮA ĂN NGON). Every target keyword below was checked to have
  // >=1 real match in data/ProductInfo/mart_vi_nsg_product.ndjson.
  // ---------------------------------------------------------------------

  const SYNONYMS = [
    ["đồ uống", "thức uống"],
    ["heo", "lợn"], ["lợn", "heo"],
    ["tôm", "tép"],
    ["ngô", "bắp"], ["bắp", "ngô"],
    ["lạc", "đậu phộng"], ["đậu phộng", "lạc"],
    ["dứa", "thơm"], ["dứa", "khóm"],
    ["rau mùi", "ngò"], ["rau mùi", "rau húng"],
    ["mì chính", "bột ngọt"], ["bột ngọt", "mì chính"],
    ["trứng gà", "hột gà"],
    ["mì ăn liền", "mì gói"], ["mì gói", "mì tôm"],
    ["nước rửa bát", "nước rửa chén"], ["nước rửa chén", "nước rửa bát"],
    ["kem đánh răng", "thuốc đánh răng"],
    ["băng vệ sinh", "bvs"],
    ["tã", "bỉm"], ["bỉm", "tã"],
    ["sữa tắm", "sữa tắm body wash"],
    ["nước ngọt", "nước giải khát"],
    ["snack", "bim bim"], ["bim bim", "snack"],
    ["dầu gội", "dầu gội đầu"],
    ["xúc xích", "lạp xưởng"],
    ["nước hoa quả", "nước trái cây"], ["nước trái cây", "nước hoa quả"],
    ["dầu ăn", "dầu thực vật"],
    ["giấy vệ sinh", "giấy toilet"],
    ["nước xịt muỗi", "muỗi"], ["thuốc xịt muỗi", "muỗi"],
    ["kem chống nắng", "sữa chống nắng"],
    ["sữa rửa mặt", "sữa rửa mặt facial"],
    ["nước lau sàn", "nước lau nhà"],
    ["nước xả vải", "nước làm mềm vải"],
    ["dầu xả", "dầu xả tóc"],
    ["kem dưỡng da", "kem dưỡng"],
    ["khăn ướt", "khăn giấy ướt"],
    ["sữa bột", "sữa công thức"],
    ["bánh quy", "bánh bích quy"],
    ["nước tương", "xì dầu"],
    ["mì Ý", "spaghetti"],
    ["gạo lứt", "gạo lức"],
    ["rượu vang", "vang đỏ"],
    ["dao cạo râu", "dao cạo"],
    ["bàn chải", "bàn chải đánh răng"],
    ["kem đánh răng", "kem chải răng"],
    ["nước rửa tay", "gel rửa tay"],
    ["thức ăn cho chó", "hạt cho chó"],
    ["thức ăn cho mèo", "hạt cho mèo"],
    ["chả lụa", "giò lụa"],
    ["mực khô", "khô mực"],
    ["tôm khô", "khô tôm"],
    ["cá basa", "cá tra"],
    ["nước suối", "nước khoáng"],
    ["nước tinh khiết", "nước lọc"],
    ["trà túi lọc", "trà lọc"],
    ["hạt nêm", "bột nêm"],
    ["nồi cơm điện", "nồi cơm"],
    ["máy xay sinh tố", "máy xay"],
    ["quạt máy", "quạt"],
    ["tã giấy", "tã"],
    ["kẹo dẻo", "kẹo mềm"],
    ["áo mưa", "áo đi mưa"],
    ["giày thể thao", "giày sneaker"],
    ["quần lót", "đồ lót"],
    ["khăn giấy", "giấy ăn"],
    ["túi rác", "bọc rác"],
    ["nước rửa rau", "nước rửa rau củ"],
    ["cải bó xôi", "rau chân vịt"],
    ["quả xoài", "xoài"], ["trái xoài", "xoài"],
    ["quả đu đủ", "đu đủ"], ["trái đu đủ", "đu đủ"],
    ["quả ổi", "ổi"], ["trái ổi", "ổi"],
    ["quả dưa hấu", "dưa hấu"], ["trái dưa hấu", "dưa hấu"],
    ["quả dưa leo", "dưa leo"], ["trái dưa leo", "dưa leo"],
    ["bánh tráng", "bánh đa nem"],
    ["nước mắm", "mắm"],
    ["cá viên", "chả cá viên"],
    ["nước giặt", "nước giặt xả"],
    ["kem ủ tóc", "hấp dầu"],
    ["sữa chua", "yaourt"],
    ["bánh trung thu", "bánh nướng"],
    ["hộp cơm", "hộp đựng cơm"],
    ["bình giữ nhiệt", "bình nước giữ nhiệt"],
    ["sữa đặc có đường", "sữa đặc"],
    ["bột giặt", "xà phòng giặt"],
    ["nước tẩy trang", "sữa tẩy trang"],
    ["khẩu trang y tế", "khẩu trang"],
    ["nước súc miệng", "nước súc họng"],
    ["hộp xốp", "hộp nhựa đựng thực phẩm"],
    ["màng bọc thực phẩm", "màng bọc"],
    ["bột nở", "baking soda"], ["men nở", "baking soda"],
    ["muối tinh", "muối i-ốt"],
    ["đường phèn", "đường cục"],
    ["hạt dinh dưỡng", "hạt sấy khô"],
    ["trái cây sấy", "trái cây khô"],
    ["nước yến", "yến sào nước"],
    ["tổ yến", "yến sào"],
    ["gạo nếp", "nếp"],
    ["nước mắm nhĩ", "nước mắm nguyên chất"],
    ["dầu mè", "dầu vừng"],
    ["ớt bột", "bột ớt"],
    ["tiêu xay", "tiêu"], ["tiêu bột", "tiêu"],
    ["cháo ăn liền", "cháo gói"],
    ["bánh quy giòn", "bánh cracker"],
    ["kẹo cao su", "chewing gum"],
    ["khăn lông", "khăn tắm"],
    ["dép lê", "dép trong nhà"], ["dép đi trong nhà", "dép trong nhà"],
    // "Quần Sọt Jean Tuệ Lâm..." is real (user caught my earlier "no jeans"
    // claim as wrong) but "Sọt" sits between "Quần" and "Jean" in the real
    // name, so the natural 2-word query "quần jean" fails the engine's
    // strict consecutive-token match and misses it entirely. Redirect to the
    // bare "jean" token (exact match, no gap) instead of the full product
    // name, so this also covers any future jean-labeled SKU, not just this one.
    ["quần jean", "jean"], ["quần bò", "jean"],
    // found by broadening searches past exact-substring matches (same lesson
    // as the jean miss) — these are real, previously-uncovered categories.
    ["cục pin", "pin"],
    ["bao tay", "găng tay"], ["găng tay", "bao tay"],
    ["dây sạc", "cáp sạc"],
    // found via real 6-month search history (top-searched, all-zero-result
    // query in the old system): "bi bi" is how users write the Korean brand
    // "bibigo" split across a space — the 2-token phrase "bi"+"bi" doesn't
    // literally appear in any product name (it's always "bibigo" as one
    // word), so redirect to the working joined form (82 real grounded hits).
    ["bi bi", "bibigo"],
    // "heniken" (real 6-month search history, score 895, all-zero in the old
    // system) is edit-distance-2 from "heineken" (missing + transposed
    // letter) — outside the typo tier's edit-distance-1 tolerance — redirect
    // explicitly rather than loosening the typo threshold catalog-wide.
    ["heniken", "heineken"],
    // "sô cô la" (spelled-out loanword, legacy/rare form — only 11 products
    // literally carry this exact spelling) vs "socola" (the compressed form
    // almost every product actually uses, 320 hits) — real search history
    // showed "sô cô la đen" (dark chocolate) as a top all-zero query even
    // though "sô cô la" alone has some hits, because none of those 11 also
    // say "đen"; redirecting to "socola" surfaces the real dark-chocolate SKUs.
    ["sô cô la", "socola"],
    // "th 1l" (brand+size shorthand, real search history score 693,
    // all-zero) for "TH true Milk" 1-liter cartons (43 real hits) — too
    // compressed for any existing tier to parse as brand+quantity.
    ["th 1l", "th true milk"],
    // Real Indexer Service synonyms API, 2026-08-25 (data/common_data/
    // indexer_synonyms_api.txt, ids 23/22/14 — DRAFT, appliedRevision=0,
    // not yet live in production). Grounded against mart_vi_nsg_product.ndjson
    // before adding (see [[project-real-search-history-data]] follow-up).
    ["sữa tươi", "sữa tươi tiệt trùng"],
    ["ký", "kg"], ["kg", "ký"],
    // "sapoche" (1 hit, real) / "hồng xiêm" (same 1 product, dual-labeled) —
    // alt-name pair, not dialect.
    ["sapoche", "hồng xiêm"], ["hồng xiêm", "sapoche"],
    // Page 2 of the same real API (ids 3/2/1, fetched 2026-08-25 later same
    // day — id 3 "nước ngọt"/"nước giải khát" already existed above, skipped).
    ["chai", "lọ"], ["lọ", "chai"],
    // id 1 "mãng cầu"<->"na": one-direction only. "mãng cầu" is cleanly
    // grounded (11 hits, all genuine fruit products). Bare "na" also matches
    // "Cá Hồi NA UY..." (Norway, unrelated) — a real homograph, same class as
    // the "roi"/"ngan" rejections above — so only na->mãng cầu is kept
    // (expanding a "na" query toward the fruit is safe; the reverse would
    // inject Norwegian-salmon noise into "mãng cầu" searches).
    ["na", "mãng cầu"],
  ];

  const REGIONAL = [
    // Real Indexer Service synonyms API, 2026-08-25 (see SYNONYMS comment
    // above for provenance/caveat). These read as Bắc/Nam dialect pairs so
    // grouped here rather than in SYNONYMS.
    ["dĩa", "đĩa"],
    // id 18 "vịt"<->"ngan": catalog has ZERO products literally named "ngan"
    // (grounded check: 0 whole-token hits) — only the ngan->vịt direction is
    // useful (real target), reverse direction would resolve to nothing.
    ["ngan", "vịt"],
    // id 15 "hộp"<->"lon": both grounded (hộp 1,750 hits, lon 326 hits) but
    // "hộp" is an extremely generic packaging word — accepted per real dev
    // data, flagged as a noise-risk (a "lon" search may surface unrelated
    // boxed items via this pair), not independently verified query-by-query.
    ["hộp", "lon"], ["lon", "hộp"],
    ["bầu", "bí"], ["bí", "bầu"],
    // id 7 "gói"<->"bịch": same generic-word caveat as hộp/lon ("gói" =
    // 2,391 hits).
    ["gói", "bịch"], ["bịch", "gói"],
    // id 6 "nồi"<->"xoong": bare-token pair, both grounded (nồi 57, xoong 2)
    // — REGIONAL already redirects "cái xoong" -> "nồi" but had no bare-word
    // pair; this covers a plain "xoong" query too.
    ["nồi", "xoong"], ["xoong", "nồi"],
    // id 5 "mận"<->"roi": catalog's 2 "roi" whole-token hits are both
    // unrelated homographs ("Bưởi Năm Roi" pomelo cultivar, "Roi Thai"
    // coconut brand line) — NOT the wax-apple fruit. Only roi->mận kept
    // (target "mận", 18 real hits); reverse omitted (ungrounded target).
    ["roi", "mận"],
    // id 4 "chanh dây"<->"chanh leo": catalog carries 0 products literally
    // named "chanh leo" (Northern term) — only chanh leo->chanh dây kept
    // (target grounded, 33 hits); reverse omitted.
    ["chanh leo", "chanh dây"],
    // Rejected candidate (NOT added), same call as the pre-existing
    // "tập"/"vở" and "cặp tóc" rejections: id 20 real API pair "trái"<->
    // "quả" is a bare single-token homograph risk — "quả" is a real, common
    // token inside unrelated abstract-noun compounds ("hiệu quả"=effective,
    // "kết quả"=result, "hậu quả"=consequence), so replacing "trái"->"quả"
    // in a query would surface unrelated non-food products. The specific
    // quả-X / trái-X pairs already in this file (quả xoài/trái xoài, etc.)
    // remain — those are multi-word and don't have this collision.
    ["dứa", "thơm"], ["dứa", "khóm"],
    ["ngô", "bắp"],
    ["lạc", "đậu phộng"],
    ["vừng", "mè"],
    ["cá quả", "cá lóc"],
    ["rau mùi", "ngò"],
    ["hành hoa", "hành lá"],
    ["quả táo", "trái táo"], ["quả cam", "trái cam"], ["quả chuối", "trái chuối"],
    ["bát", "chén"],
    ["cốc", "ly"],
    ["thìa", "muỗng"],
    ["chăn", "mền"],
    ["áo phông", "áo thun"],
    ["mì chính", "bột ngọt"],
    ["trứng gà", "hột gà"],
    ["tã", "bỉm"],
    ["rổ", "rá"],
    ["thịt ba chỉ", "thịt ba rọi"],
    ["đậu phụ", "đậu hủ"],
    ["tất", "vớ"],
    ["mỳ", "mì"],
    ["cái nồi", "nồi"], ["cái xoong", "nồi"],
    ["nước hoa quả", "nước ép trái cây"],
    ["đường cát", "đường tinh luyện"], ["đường trắng", "đường tinh luyện"],
    ["hành", "hành tây"],
    ["quả xoài", "xoài"], ["trái xoài", "xoài"],
    ["quả đu đủ", "đu đủ"], ["trái đu đủ", "đu đủ"],
    ["quả ổi", "ổi"], ["trái ổi", "ổi"],
    ["quả dưa hấu", "dưa hấu"], ["trái dưa hấu", "dưa hấu"],
    ["bánh tráng", "bánh đa nem"],
    ["mực khô", "khô mực"], ["tôm khô", "khô tôm"],
    ["quả dưa leo", "dưa leo"], ["trái dưa leo", "dưa leo"],
    ["dưa leo", "dưa chuột"],
    ["rau dền", "dền"],
    ["bí đỏ", "bí ngô"],
    ["khoai mì", "sắn"],
    ["hủ", "hộp"],
    ["bánh chưng", "bánh tét"],
    ["mũ", "nón"],
  ];

  // intent/purpose phrase -> real, grounded target keywords in NSG catalog
  const INTENT = {
    "gym": ["thảm tập yoga", "bình nước thể thao", "quần short"],
    "jym": ["thảm tập yoga", "bình nước thể thao", "quần short"],
    "tập gym": ["thảm tập yoga", "bình nước thể thao", "quần short"],
    "tập thể hình": ["thảm tập yoga", "bình nước thể thao"],
    "yoga": ["thảm tập yoga", "quần short"],
    "tập yoga": ["thảm tập yoga"],
    "đi mưa": ["áo mưa", "dù"],
    "trời mưa": ["áo mưa", "dù"],
    "đi bơi": ["kính bơi"],
    "bơi lội": ["kính bơi"],
    "em bé": ["tã", "bỉm", "sữa bột", "khăn ướt", "bánh ăn dặm", "đồ chơi"],
    "trẻ sơ sinh": ["tã", "bỉm", "sữa bột", "khăn ướt"],
    "đồ ăn cho bé": ["bánh ăn dặm", "sữa bột"],
    "thức ăn cho bé": ["bánh ăn dặm", "sữa bột"],
    "sơ sinh": ["tã", "bỉm", "khăn ướt"],
    "nấu ăn": ["gạo", "dầu ăn", "nước mắm", "gia vị"],
    "vào bếp": ["gạo", "dầu ăn", "nước mắm", "gia vị"],
    "nấu cơm": ["gạo", "nồi cơm"],
    "ăn vặt": ["bánh kẹo", "snack", "kẹo dẻo", "mì ăn liền"],
    "đói bụng": ["mì ăn liền", "bánh mì", "snack"],
    "thèm ăn": ["bánh kẹo", "snack"],
    "tiệc tùng": ["bia", "nước ngọt", "bánh kẹo"],
    "liên hoan": ["bia", "nước ngọt", "bánh kẹo"],
    "party": ["bia", "nước ngọt", "bánh kẹo"],
    "pha cà phê": ["cà phê"],
    "buồn ngủ": ["cà phê", "trà"],
    "tỉnh táo": ["cà phê"],
    "giặt đồ": ["bột giặt", "nước xả vải"],
    "giặt quần áo": ["bột giặt", "nước xả vải"],
    "rửa chén": ["nước rửa chén"],
    "rửa bát": ["nước rửa chén"],
    "dọn nhà": ["nước lau sàn", "khăn lau"],
    "lau nhà": ["nước lau sàn"],
    "vệ sinh nhà cửa": ["nước lau sàn", "khăn lau"],
    "làm đẹp": ["sữa rửa mặt", "kem dưỡng", "mặt nạ"],
    "chăm sóc da": ["sữa rửa mặt", "kem dưỡng", "mặt nạ", "kem chống nắng"],
    "dưỡng da": ["kem dưỡng", "mặt nạ"],
    "gội đầu": ["dầu gội"],
    "chăm sóc tóc": ["dầu gội", "dầu xả"],
    "đánh răng": ["kem đánh răng", "bàn chải đánh răng"],
    "vệ sinh răng miệng": ["kem đánh răng", "bàn chải đánh răng"],
    "cạo râu": ["dao cạo"],
    "thú cưng": ["thức ăn cho chó", "thức ăn cho mèo"],
    "nuôi chó": ["thức ăn cho chó"],
    "nuôi mèo": ["thức ăn cho mèo"],
    "bồi bổ sức khỏe": ["mật ong", "vitamin", "tổ yến", "tinh bột nghệ"],
    "tăng đề kháng": ["mật ong", "vitamin c", "tổ yến"],
    "cảm cúm": ["mật ong", "vitamin c"],
    "giảm cân": ["gạo lứt", "ngũ cốc"],
    "ăn kiêng": ["gạo lứt", "ngũ cốc"],
    "đi làm": ["bút", "cà phê"],
    "đi học": ["bút", "bút chì"],
    "văn phòng phẩm": ["bút", "bút chì", "bút gel"],
    "nướng bbq": ["thịt", "xúc xích"],
    "tiệc nướng": ["thịt", "xúc xích"],
    "lễ tết": ["hộp quà", "mật ong", "bánh kẹo"],
    "quà biếu": ["hộp quà", "mật ong"],
    "nhậu": ["bia", "rượu vang"],
    "uống trà": ["trà"],
    "ăn lẩu": ["lẩu", "rau", "thịt"],
    "nấu lẩu": ["lẩu"],
    "ăn sáng": ["sữa tươi", "ngũ cốc", "bánh mì"],
    "bữa sáng": ["sữa tươi", "ngũ cốc", "bánh mì"],
    "chiên xào": ["chảo", "dầu ăn"],
    "khử khuẩn": ["nước rửa tay"],
    "rửa tay": ["nước rửa tay"],
    "muỗi": ["xịt muỗi"],
    "côn trùng": ["xịt muỗi"],
    "trang điểm": ["mặt nạ", "kem dưỡng"],
    "nắng nóng": ["kem chống nắng"],
    "chống nắng": ["kem chống nắng"],
    "sinh nhật": ["bánh kem", "nến sinh nhật", "kẹo"],
    "đám cưới": ["rượu vang", "hộp quà"],
    "ăn chay": ["nước mắm chay", "đậu hủ"],
    "detox": ["mật ong", "trái cây"],
    "làm bánh": ["bột mì", "trứng gà", "bơ"],
    "nướng bánh": ["bột mì", "khuôn bánh"],
    "pha sữa": ["sữa bột", "bình sữa"],
    "cho con bú": ["sữa bột", "bình sữa", "khăn ướt"],
    "tắm cho bé": ["sữa tắm em bé", "khăn tắm em bé"],
    "hăm tã": ["tã", "khăn ướt"],
    "mọc răng": ["bánh ăn dặm"],
    "ăn dặm": ["bánh ăn dặm", "sữa bột"],
    "đi du lịch": ["hộp quà", "khăn ướt"],
    "cắm trại": ["mì ăn liền", "nước ngọt"],
    "dã ngoại": ["bánh kẹo", "nước ngọt"],
    "xem phim": ["bắp rang bơ", "nước ngọt", "snack"],
    "coi bóng đá": ["bia", "snack"],
    "trời lạnh": ["trà", "cà phê"],
    "trời nóng": ["nước ngọt", "kem"],
    "say xe": ["kẹo gừng"],
    "đau họng": ["mật ong"],
    "mất ngủ": ["trà"],
    "rụng tóc": ["dầu gội"],
    "gàu": ["dầu gội"],
    "khô da": ["kem dưỡng"],
    "mụn": ["sữa rửa mặt", "miếng dán mụn"],
    "trị mụn": ["miếng dán mụn", "sữa rửa mặt"],
    "hôi miệng": ["kem đánh răng", "nước súc miệng"],
    "hôi nách": ["lăn khử mùi"],
    "muỗi đốt": ["xịt muỗi"],
    "kiến gián": ["thuốc xịt côn trùng"],
    "sạch nhà": ["nước lau sàn", "nước rửa chén"],
    "khử mùi tủ lạnh": ["baking soda"],
    "rửa rau": ["nước rửa rau củ"],
    "nấu chiên": ["dầu ăn", "chảo"],
    "nấu canh": ["nước mắm", "hạt nêm"],
    "nấu súp": ["kem tươi"],
    "làm salad": ["dầu ô liu", "sốt mayonnaise"],
    "ăn kèm cơm": ["nước mắm", "ruốc"],
    "uống bia": ["bia", "snack"],
    "uống rượu": ["rượu vang", "rượu mạnh"],
    "pha trà sữa": ["trà", "sữa đặc"],
    "giải khát": ["nước ngọt", "trà"],
    "bù nước": ["nước khoáng"],
    "tăng cân": ["sữa bột"],
    "trẻ biếng ăn": ["sữa bột"],
    "người già": ["sữa bột", "vitamin"],
    "phụ nữ mang thai": ["vitamin", "sữa bột"],
    "dọn vệ sinh thú cưng": ["cát vệ sinh cho mèo"],
    "sơn móng tay": ["bấm móng tay"],
    "cạo lông": ["dao cạo"],
    "tẩy trang": ["nước tẩy trang"],
    "dưỡng môi": ["son dưỡng môi"],
    "giặt tay": ["xà bông"],
    "gấp quần áo": ["móc áo"],
    "đựng thực phẩm": ["hộp đựng thực phẩm"],
    "bảo quản lạnh": ["hộp đựng thực phẩm"],
    "đóng gói quà": ["hộp quà"],
    "viết bài": ["bút", "vở"],
    "tô màu": ["bút chì màu"],
    "học sinh": ["bút", "vở", "balo"],
    "nấu cháo": ["gạo"],
    "nấu phở": ["bánh phở", "thịt bò"],
    "nấu bún": ["bún", "thịt bò"],
    "nấu mì": ["mì", "trứng gà"],
    "kho cá": ["nước mắm", "đường"],
    "kho thịt": ["nước mắm", "đường"],
    "ướp thịt": ["nước mắm", "hạt nêm"],
    "pha nước chấm": ["nước mắm", "đường"],
    "làm bánh flan": ["trứng gà", "sữa đặc"],
    "trang trí sinh nhật": ["nến sinh nhật", "bánh kem"],
    "tiếp khách": ["bia", "nước ngọt", "bánh kẹo"],
    "về quê": ["hộp quà", "bánh kẹo"],
    "đi phượt": ["mì ăn liền", "nước khoáng"],
    "làm việc tại nhà": ["cà phê", "trà"],
    "mùa thi": ["cà phê", "kẹo"],
    "thức khuya": ["cà phê"],
    "dưỡng tóc hư tổn": ["dầu xả"],
    "tóc khô xơ": ["dầu xả"],
    "da dầu": ["sữa rửa mặt"],
    "da nhạy cảm": ["kem dưỡng"],
    "chăm sóc em bé sơ sinh": ["tã", "khăn ướt", "sữa tắm"],
    "bé tập đi": ["sữa bột", "bánh ăn dặm"],
    "bé đi học": ["balo", "bút"],
    "chuẩn bị năm học mới": ["bút", "vở", "balo"],
    "nấu chè": ["đường", "đậu xanh"],
    "làm sữa chua": ["sữa đặc", "sữa chua"],
    "ăn chay trường": ["nước mắm chay", "đậu hủ"],
    "detox giảm cân": ["mật ong", "trái cây"],
    "bồi bổ sau ốm": ["tổ yến", "mật ong"],
    "trẻ sốt mọc răng": ["bánh ăn dặm"],
    "khách đến nhà bất ngờ": ["bánh kẹo", "nước ngọt"],
    "mua đồ nhậu": ["bia", "snack"],
    "nấu nước lẩu": ["lẩu"],
    "ăn kiêng low carb": ["gạo lứt"],
    "ăn eat clean": ["gạo lứt", "ngũ cốc"],
    "khử mùi cơ thể": ["lăn khử mùi"],
    "rửa mặt buổi sáng": ["sữa rửa mặt"],
    "dưỡng ẩm da": ["kem dưỡng"],
    "tựu trường": ["bút", "vở", "balo"],
    "xem world cup": ["bia", "snack"],
    "trung thu": ["bánh trung thu"],
    "tết trung thu": ["bánh trung thu"],
    "quà valentine": ["hộp quà"],
    "quà 8/3": ["hộp quà"],
    "quà 20/10": ["hộp quà"],
    "quà noel": ["bánh kẹo", "hộp quà"],
    "gói bánh chưng": ["bánh chưng"],
    "ăn tết": ["bánh chưng", "mật ong", "bánh kẹo", "hộp quà"],
    "biếu tết": ["hộp quà", "mật ong"],
    "nấu bánh chưng": ["bánh chưng"],
    "mùa đông": ["trà", "cà phê"],
    "mùa hè": ["kem chống nắng", "nước ngọt", "kem"],
    "trời hanh khô": ["kem dưỡng"],
    "da khô": ["kem dưỡng"],
    "tóc dầu": ["dầu gội"],
    "khử mùi giày": ["baking soda"],
    "khử mùi tủ giày": ["baking soda"],
    "vệ sinh máy giặt": ["baking soda"],
    "ăn kiêng giảm cân": ["gạo lứt", "ngũ cốc"],
    "bổ sung vitamin": ["vitamin", "vitamin c"],
    "tăng sức đề kháng": ["vitamin c", "tổ yến", "mật ong"],
    "trẻ em đi học": ["bút", "vở", "balo"],
    "đi phỏng vấn": ["bút"],
    "họp mặt gia đình": ["bánh kẹo", "nước ngọt", "hộp quà"],
    "tân gia": ["hộp quà"],
    "thôi nôi": ["bánh kẹo", "hộp quà"],
    "đầy tháng": ["bánh kẹo", "hộp quà"],
    "cúp điện": ["đèn pin", "pin"],
    "mất điện": ["đèn pin", "pin"],
    "cống nghẹt": ["thông cống"],
    "nghẹt cống": ["thông cống"],
    "toilet nghẹt": ["thông cống"],
    "rửa chén không dùng găng tay": ["găng tay"],
    "thay pin đồ chơi": ["pin"],
    "thay pin điều khiển": ["pin"],
  };

  // Natural browsing phrase -> real NSG level-2 category label. Raw category
  // fields are literal strings like "THỰC PHẨM TƯƠI SỐNG / Trái Cây" — nobody
  // browsing types that, they type "hoa quả" or "mua trái cây tươi". Same
  // grounded-phrase-to-target shape as INTENT above, just targeting catTokens.
  const CATEGORY = {
    "bánh kẹo": "Bánh Kẹo", "đồ ăn vặt": "Bánh Kẹo", "snack ăn vặt": "Bánh Kẹo",
    "đồ gia dụng": "Nhà Cửa Đời Sống", "đồ dùng nhà bếp": "Nhà Cửa Đời Sống",
    "chăm sóc cá nhân": "Chăm Sóc Cá Nhân", "đồ vệ sinh cá nhân": "Chăm Sóc Cá Nhân",
    "dầu ăn gia vị": "Dầu Ăn, Gia Vị", "gia vị nấu ăn": "Dầu Ăn, Gia Vị",
    "gạo mì bún": "Gạo, Mì, Bún, Đậu", "đồ khô nấu ăn": "Gạo, Mì, Bún, Đậu",
    "nước tẩy rửa": "Hóa Phẩm, Vệ Sinh", "hoá phẩm vệ sinh": "Hóa Phẩm, Vệ Sinh",
    "sản phẩm từ sữa": "Chế Phẩm Từ Sữa", "đồ uống từ sữa": "Chế Phẩm Từ Sữa",
    "nước giải khát": "Đồ Uống", "đồ uống": "Đồ Uống",
    "đồ đông lạnh": "Thực Phẩm Đông Lạnh", "thực phẩm đông lạnh": "Thực Phẩm Đông Lạnh",
    "trà cà phê": "Trà, Cà Phê", "đồ uống nóng": "Trà, Cà Phê",
    "đồ dùng mẹ và bé": "Mẹ Và Bé", "đồ sơ sinh": "Mẹ Và Bé",
    "chăm sóc sức khoẻ": "Sức Khỏe, Làm Đẹp", "làm đẹp": "Sức Khỏe, Làm Đẹp",
    // "mỹ phẩm" (cosmetics) is a top-searched real term (6-month history)
    // with zero name/brand/description hits — no SKU is literally named or
    // tagged "mỹ phẩm", but it's the natural umbrella term for this category.
    "mỹ phẩm": "Sức Khỏe, Làm Đẹp",
    "rau củ tươi": "Rau Củ", "rau xanh": "Rau Củ",
    "thịt tươi sống": "Thịt", "thịt các loại": "Thịt",
    "quần áo": "Thời Trang", "đồ thời trang": "Thời Trang",
    "đồ ăn nhanh": "Món Ăn Nhanh", "món ăn liền": "Món Ăn Nhanh",
    "hải sản tươi": "Thủy sản", "đồ biển": "Thủy sản",
    "trái cây tươi": "Trái Cây", "hoa quả": "Trái Cây",
    "đồ điện gia dụng": "Điện Gia Dụng", "thiết bị điện": "Điện Gia Dụng",
    "bánh mì tươi": "Bánh Tươi", "bánh ngọt": "Bánh Tươi",
    "thực phẩm bổ sung": "Thực Phẩm Bổ Sung", "đồ bồi bổ sức khoẻ": "Thực Phẩm Bổ Sung",
    "đồ sơ chế sẵn": "Thực Phẩm Sơ Chế", "thực phẩm chế biến sẵn": "Thực Phẩm Sơ Chế",
    "đồ cho thú cưng": "Thú Cưng", "phụ kiện chó mèo": "Thú Cưng",
    "trứng các loại": "Trứng",
    "đồ thể thao": "Thể Thao", "dụng cụ thể thao": "Thể Thao",
    "rượu vang": "Rượu Vang",
    "rượu mạnh": "Rượu Mạnh",
    "bia các loại": "Bia",
    "đồ chơi trẻ em": "Đồ Chơi, Thú Bông", "thú bông": "Đồ Chơi, Thú Bông",
    "đồ chăm sóc bé": "Chăm Sóc Bé",
    "cá viên xúc xích": "Cá Viên, Xúc Xích",
  };

  // Words/phrases a suggestion must NEVER surface as — matches SS-SCR-001-
  // SC3-TC3 in the production test suite ("Keywords with 0 results or
  // banned words are never shown"). This is a SEPARATE rule from
  // groundedness: a banned word is hidden even if it's grounded (real
  // products exist), and groundedness alone doesn't excuse a banned word —
  // both checks must pass. Deliberately empty: no real wordlist has been
  // supplied yet (profanity, competitor brand names, or anything else QA/BA
  // flags). Add real entries here when given one; matching is
  // diacritics-stripped and substring-based (isBannedKeyword below) so a
  // banned word is still caught if typed without accents or embedded inside
  // a longer suggested phrase.
  const BANNED_WORDS = [];
  function isBannedKeyword(keyword) {
    if (!BANNED_WORDS.length) return false;
    const kwNorm = normalize(keyword);
    return BANNED_WORDS.some((w) => {
      const wn = normalize(w);
      return !!wn && kwNorm.indexOf(wn) !== -1;
    });
  }

  // ---------------------------------------------------------------------
  // Text utilities
  // ---------------------------------------------------------------------

  function stripDiacritics(s) {
    return String(s || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D")
      // NFD canonically decomposes non-Latin scripts too (e.g. Hangul syllables
      // split into Jamo components) even though they have no diacritic to strip;
      // recompose so tokens() below sees whole Hangul syllables again, not a
      // string of orphaned Jamo that its [a-z0-9...] word-char class would drop.
      .normalize("NFC");
  }
  function normalize(s) {
    // "&"/"/" are dropped (not treated as separators) ONLY when they sit
    // directly between two characters with no surrounding space, so a
    // brand-style acronym like "P&G"/"H&M"/"P/S" collapses into one token
    // ("pg"/"hm"/"ps") instead of two 1-char tokens the length>=2 filter
    // below would silently discard (found via real 6-month search history:
    // "p/s" — P/S toothpaste — was a top-searched, all-zero-result query in
    // the old system). Deliberately NOT stripped when spaced ("A / B", "X &
    // Y") — that would wrongly fuse unrelated words together, e.g. the
    // "THỰC PHẨM KHÔ / Bánh Kẹo" category-path separator, or real product
    // names like "Xương Ống & Tủy" (bone & marrow) / "Trà & Hoa Lài" (tea &
    // jasmine) where "&" genuinely joins two distinct searchable words.
    return stripDiacritics(String(s || "").toLowerCase()).replace(/(?<=\S)[&/](?=\S)/g, "").trim();
  }
  // Word-char class: ASCII alnum + Hangul syllables (가-힣), so Korean
  // catalog/query text tokenizes into real syllable tokens instead of being
  // silently dropped by an ASCII/Vietnamese-only class.
  function tokens(s) {
    return normalize(s).split(/[^a-z0-9가-힣]+/).filter((t) => t.length >= 2);
  }
  function tokensCaseFold(s) {
    // like tokens(), but keeps diacritics — for the strict "exact" tier
    return String(s || "").toLowerCase().replace(/(?<=\S)[&/](?=\S)/g, "").split(/[^a-z0-9à-ỹ]+/i).filter((t) => t.length >= 2);
  }
  // No-diacritics Vietnamese function words (prepositions/conjunctions/etc.)
  // — same list used by export_full_store_catalog.py's description-keyword
  // extraction. Excluded from the "partial" last-resort tier: a bare function
  // word like "cho" (for) is >=3 chars and appears in huge numbers of
  // unrelated product names, so letting it count as a match makes "partial"
  // fire on essentially any query, not just ones sharing real subject words.
  const STOPWORDS_VI = new Set([
    "va", "hoac", "la", "cua", "cho", "voi", "tai", "trong", "khi", "sau", "truoc",
    "de", "duoc", "khong", "co", "mot", "cac", "nhung", "nay", "do", "nen", "the",
    "san", "pham", "theo", "tu", "den", "neu", "hay", "vao", "ra", "len", "xuong",
    "nhu", "boi", "vi", "ma", "thi", "day", "kia", "moi", "rat", "qua", "con",
    "chi", "ban", "quy", "khach", "vui", "long", "xem", "chinh", "sach",
  ]);

  // Phrase-prefix containment: does `needle` (token array) appear as a
  // CONSECUTIVE run inside `hay` (token array), where every needle token
  // except the last must match a hay token exactly, and the last needle
  // token may match exactly OR be a prefix of the corresponding hay token?
  // This is what a real search-as-you-type index does, and it is what
  // prevents queries like "bim" from matching inside "Bibimbap" or "em be"
  // from matching across the word boundary in "Kem Benuscream" — plain
  // substring search on the joined string does neither.
  function phraseContains(hay, needle, allowPrefixOnLast) {
    if (allowPrefixOnLast === undefined) allowPrefixOnLast = true;
    if (!needle.length || !hay.length || needle.length > hay.length) return false;
    for (let start = 0; start <= hay.length - needle.length; start++) {
      let ok = true;
      for (let i = 0; i < needle.length; i++) {
        const h = hay[start + i];
        const n = needle[i];
        const isLast = i === needle.length - 1;
        if (isLast && allowPrefixOnLast ? !h.startsWith(n) : h !== n) {
          ok = false;
          break;
        }
      }
      if (ok) return true;
    }
    return false;
  }
  // Like phraseContains, but each needle token may also match a hay token that's
  // within edit distance 1 (typo-tolerant) instead of requiring exact/prefix —
  // used for the typo tier so a misspelling in ANY one word of a multi-word
  // query ("coa cola" for "coca cola") is still forgiven, not just single-word
  // queries.
  function phraseContainsFuzzy(hay, needle, editDistFn) {
    if (!needle.length || !hay.length || needle.length > hay.length) return false;
    for (let start = 0; start <= hay.length - needle.length; start++) {
      let ok = true;
      for (let i = 0; i < needle.length; i++) {
        const h = hay[start + i];
        const n = needle[i];
        if (h === n) continue;
        if (n.length >= 3 && Math.abs(h.length - n.length) <= 2 && editDistFn(h, n, 1)) continue;
        ok = false;
        break;
      }
      if (ok) return true;
    }
    return false;
  }
  // Bag-of-words AND match, order doesn't matter — used for description
  // keywords, which are a deduped keyword list, not a grammatical phrase.
  // Only the LAST needle token gets prefix tolerance (mirrors phraseContains'
  // as-you-type rule); every earlier token must match a hay token exactly.
  // Prefix-matching EVERY token here was a real bug: "mun" (from "mụn"/acne)
  // is 3+ chars so it passed the length gate and then prefix-matched "mung"
  // (from "mừng"/happy, e.g. "chúc mừng" in an unrelated flower product's
  // description) even though the query "trị mụn" was fully typed — the query
  // "trị mụn" scoring an unrelated Chậu Hoa Hồng via this path is exactly the
  // failure this restriction closes, since "tri" now requires an exact hay
  // token and there is none in that product's description.
  function bagContainsAll(hay, needle) {
    if (!needle.length) return false;
    return needle.every((n, i) => {
      if (n.length < 3) return false;
      const isLast = i === needle.length - 1;
      return hay.some((h) => h === n || (isLast && h.startsWith(n)));
    });
  }
  // crude HTML strip for description fields
  function stripHtml(s) {
    return String(s || "").replace(/<[^>]*>/g, " ").replace(/&[a-z]+;/gi, " ");
  }

  function editDistanceLE(a, b, maxDist) {
    // Damerau-Levenshtein (OSA variant: adjacent transposition counts as 1 edit,
    // not 2) so common human typos like swapped keys ("vinamlik" for "vinamilk")
    // register as a single-character-equivalent typo, matching how people
    // actually mistype rather than pure Levenshtein insert/delete/substitute.
    if (Math.abs(a.length - b.length) > maxDist) return false;
    const m = a.length, n = b.length;
    const dp = [];
    for (let i = 0; i <= m; i++) dp.push(new Array(n + 1).fill(0));
    for (let i = 0; i <= m; i++) dp[i][0] = i;
    for (let j = 0; j <= n; j++) dp[0][j] = j;
    for (let i = 1; i <= m; i++) {
      for (let j = 1; j <= n; j++) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
          dp[i][j] = Math.min(dp[i][j], dp[i - 2][j - 2] + 1);
        }
      }
    }
    return dp[m][n] <= maxDist;
  }

  // ---------------------------------------------------------------------
  // Product indexing
  // ---------------------------------------------------------------------

  // Inverted-index helpers. A brute-force scoreProduct() over all ~16k
  // products per search() call is fine for a handful of ad-hoc queries, but
  // autocomplete() re-searches ~100 candidate keywords per outer query for
  // groundedness validation, which multiplies out to millions of full scans
  // over a 1000-query batch. To keep both the batch precompute and any live
  // in-artifact query responsive, we build a token -> product-indices
  // postings map (plus a sorted token list for prefix lookups) once, and use
  // it to narrow scoreProduct() down to a small candidate set per query. The
  // postings-based candidate set is always a SUPERSET of true matches (never
  // narrower), so precision is unaffected — only the number of scoreProduct
  // calls shrinks.
  function buildTokenIndex(tokenListsPerEntry) {
    const map = new Map();
    for (let i = 0; i < tokenListsPerEntry.length; i++) {
      const uniq = new Set(tokenListsPerEntry[i]);
      for (const t of uniq) {
        let arr = map.get(t);
        if (!arr) { arr = []; map.set(t, arr); }
        arr.push(i);
      }
    }
    const sorted = Array.from(map.keys()).sort();
    return { map, sorted };
  }
  function lowerBound(sorted, target) {
    let lo = 0, hi = sorted.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (sorted[mid] < target) lo = mid + 1; else hi = mid;
    }
    return lo;
  }
  function prefixRange(sorted, prefix) {
    const out = [];
    for (let i = lowerBound(sorted, prefix); i < sorted.length; i++) {
      if (sorted[i].indexOf(prefix) === 0) out.push(sorted[i]);
      else break;
    }
    return out;
  }
  function postingsUnion(idx, tokenList) {
    const set = new Set();
    for (const t of tokenList) {
      const arr = idx.map.get(t);
      if (arr) for (const p of arr) set.add(p);
    }
    return set;
  }
  // Candidates for a consecutive-phrase query (mirrors phraseContains): every
  // token but the last must match a postings entry exactly; the last token
  // may prefix-match. Superset of phraseContains()'s true positives.
  function candidatesForPhrase(idx, qTokens, allowPrefixOnLast) {
    if (!qTokens.length) return new Set();
    let result = null;
    for (let i = 0; i < qTokens.length; i++) {
      const isLast = i === qTokens.length - 1;
      const postings = (isLast && allowPrefixOnLast)
        ? postingsUnion(idx, prefixRange(idx.sorted, qTokens[i]))
        : new Set(idx.map.get(qTokens[i]) || []);
      if (result === null) result = postings;
      else {
        const inter = new Set();
        for (const x of result) if (postings.has(x)) inter.add(x);
        result = inter;
      }
      if (result.size === 0) break;
    }
    return result || new Set();
  }
  // Candidates for a bag/AND query (mirrors bagContainsAll): every needle
  // token (>=3 chars) must prefix-match SOME hay token, order irrelevant.
  function candidatesForBag(idx, needleTokens) {
    if (!needleTokens.length) return new Set();
    for (const n of needleTokens) if (n.length < 3) return new Set();
    let result = null;
    for (const n of needleTokens) {
      const postings = postingsUnion(idx, prefixRange(idx.sorted, n));
  result = result === null ? postings : new Set([...result].filter((x) => postings.has(x)));
      if (result.size === 0) break;
    }
    return result || new Set();
  }
  // Typo-tier candidates: instead of fuzzy-checking every product's name
  // against the query (the O(16k) scan that dominated batch runtime), bucket
  // unique name tokens by length (edit-distance-1 implies length differs by
  // at most 1) and only run editDistanceLE against tokens in the neighboring
  // buckets — typically dozens, not thousands. Candidate generation only;
  // scoreProduct() still does the precise phraseContainsFuzzy verification.
  function typoCandidates(idxNameOnly, qTokens) {
    const out = new Set();
    for (const qt of qTokens) {
      if (qt.length < 3) continue;
      for (let len = qt.length - 1; len <= qt.length + 1; len++) {
        const bucket = idxNameOnly.byLength.get(len);
        if (!bucket) continue;
        for (const t of bucket) {
          if (t === qt) continue;
          if (editDistanceLE(t, qt, 1)) {
            for (const p of idxNameOnly.map.get(t)) out.add(p);
          }
        }
      }
    }
    return out;
  }

  // Rule 2 (BA meeting 2026-08-24): "OpenSearch + Elasticsearch phối hợp...
  // Elasticsearch chỉ cho hiển thị sản phẩm đang Active" - an inactive
  // product must never surface at all, regardless of match quality, so it's
  // filtered out of the CANDIDATE POOL here (buildIndex), not just scored low.
  // Field choice: `status` (Magento's own catalog_product status attribute -
  // 1=Enabled, 2=Disabled, matches this system's real "Sign in with Magento"
  // SSO stack) per the user's explicit call - "tạm lấy status... TBC BA/Dev"
  // (temporarily use `status`, still To-Be-Confirmed with BA/Dev; the raw
  // catalog also carries ec_status/visibility_search/visibility_catalog,
  // which might turn out to be the more correct field - revisit if BA/Dev say
  // otherwise, see AI_CONTEXT.md §3e). Products missing `status` entirely
  // (older exported fixtures without this field) are treated as Active, for
  // backward compatibility with catalogs that predate this rule.
  function isActiveProduct(p) {
    return p.status === undefined || p.status === null || p.status === 1;
  }

  function buildIndex(products) {
    products = products.filter(isActiveProduct);
    const entries = products.map((p) => ({
      p,
      nameCaseFoldTokens: tokensCaseFold(p.name),
      nameTokens: tokens(p.name),
      nameEnTokens: tokens(p.name_en),
      nameKrTokens: tokens(p.name_kr),
      // Diacritics-preserved (case-fold only), NOT tone-stripped like tokens().
      // desc_kw is a loose bag of boilerplate/marketing words, so the odds of
      // an unrelated word colliding after tone-stripping are much higher than
      // for a tightly-curated product name: "trị" (treat/cure) and "trì" (as
      // in "duy trì"/maintain) both stripped to "tri", so query "trị mụn"
      // exact-matched an unrelated flower product's description that happened
      // to contain "duy trì" + "mừng" (which similarly collided with "mụn"
      // via prefix). Tone marks carry real meaning in Vietnamese and a bag of
      // loosely-related words is exactly where that ambiguity bites hardest,
      // so description matching requires the query to carry correct diacritics.
      descTokens: tokensCaseFold(p.desc_kw),
      catTokens: tokens(p.cat),
      // Diacritics-preserved like name tokens (brand names are usually proper
      // nouns/loanwords — "P&G", "Unilever", "Vinamilk" — case-fold matching
      // is the right strictness, same reasoning as nameCaseFoldTokens).
      brandTokens: tokensCaseFold(p.brand),
      popularity: (p.sold30 || 0) * 3 + (p.viewed || 0) * 0.2,
    }));
    // idxCaseFold: diacritics-preserved product-name + brand + description
    // tokens (exact tier, brand tier, description tier, and synonym/intent
    // target matching, which are all deliberately diacritics-strict — see the
    // descTokens comment above for why description joined this group).
    // Pooling is a safe superset for candidate generation — scoreProduct()
    // still checks each field specifically to attribute the correct tier;
    // this pooling only affects which products get CONSIDERED, not scoring.
    const idxCaseFold = buildTokenIndex(entries.map((e) => e.nameCaseFoldTokens.concat(e.brandTokens, e.descTokens)));
    // idxNorm: no-diacritics tokens pooled across name/en/kr/cat — a safe
    // union superset for the no_diacritics/multilang/category tiers.
    const idxNorm = buildTokenIndex(entries.map((e) =>
      e.nameTokens.concat(e.nameEnTokens, e.nameKrTokens, e.catTokens)));
    // idxNameOnly: name tokens only, length-bucketed, for the typo-candidate scan.
    const idxNameOnly = buildTokenIndex(entries.map((e) => e.nameTokens));
    idxNameOnly.byLength = new Map();
    for (const t of idxNameOnly.sorted) {
      const len = t.length;
      let bucket = idxNameOnly.byLength.get(len);
      if (!bucket) { bucket = []; idxNameOnly.byLength.set(len, bucket); }
      bucket.push(t);
    }
    return { entries, idxCaseFold, idxNorm, idxNameOnly };
  }

  // Returns [{phrase, tok}] alternate phrasings from synonym/regional glossaries
  // whose SOURCE phrase is present in the query (matched loosely, no-diacritics,
  // since we're interpreting fuzzy user input here). `tok` is the TARGET
  // phrase's diacritics-PRESERVED token form — deliberately not run through the
  // no-diacritics normalizer, because short Vietnamese glossary targets (e.g.
  // "tã"->"ta", "dù"->"du") collide with unrelated common words once their
  // diacritics are stripped ("ta" in "Gà Ta", "du" in "Đu Đủ"). The glossary
  // author (me) already knows the exact target spelling, so match it exactly.
  function expandQueryTerms(qTokens, qCaseFoldTokens, qNorm) {
    const out = [];
    const seen = new Set();
    const add = (phrase) => {
      const tok = tokensCaseFold(phrase);
      const key = tok.join(" ");
      if (tok.length && !seen.has(key)) {
        seen.add(key);
        out.push({ phrase, tok });
      }
    };
    // A single-word glossary source is collision-prone once diacritics are
    // stripped: "tã" -> "ta" collides with the pronoun "ta" ("gà TA" = local
    // chicken), "nồi" -> "noi" collides with "nói" (to speak). Multi-word
    // sources are much safer (several tokens coincidentally aligning is
    // rare), so only single-token sources need the stricter check — require
    // the diacritics-PRESERVED token to match exactly, not the lenient
    // no-diacritics form. This intentionally means a bare one-word glossary
    // source only fires when typed with correct accents; that's the right
    // trade — the no_diacritics test dimension exercises product NAMES
    // directly, not glossary sources, so it isn't affected.
    const sourceMatches = (phrase) => {
      const st = tokens(phrase);
      if (st.length === 1) {
        const scf = tokensCaseFold(phrase);
        return scf.length === 1 && !!qCaseFoldTokens && qCaseFoldTokens.includes(scf[0]);
      }
      return phraseContains(qTokens, st, false);
    };
    for (const [a, b] of SYNONYMS) {
      if (sourceMatches(a)) add(b);
      if (sourceMatches(b)) add(a);
    }
    for (const [a, b] of REGIONAL) {
      if (sourceMatches(a)) add(b);
      if (sourceMatches(b)) add(a);
    }
    // "chó" (dog) and "cho" (the extremely common preposition "for/give")
    // are homographs once diacritics are stripped — and here the SOURCE
    // phrase itself is multi-word ("đồ ăn chó"), so the single-token rule
    // above doesn't cover it: the whole 3-token run still happens to prefix-
    // align with any "đồ ăn cho X" sentence once "chó" strips to "cho". Check
    // the diacritics-preserved tokens directly for this specific pair.
    if (qCaseFoldTokens && (qCaseFoldTokens.includes("ăn") || qCaseFoldTokens.includes("đồ") || qCaseFoldTokens.includes("thức"))) {
      if (qCaseFoldTokens.includes("chó")) add("thức ăn cho chó");
      if (qCaseFoldTokens.includes("mèo")) add("thức ăn cho mèo");
    }
    // "m & m" (spaced ampersand, found via real 6-month search history as a
    // top-searched all-zero-result query): each side is a single letter, so
    // tokens()/tokensCaseFold() drop both as <2-char tokens and the normal
    // SYNONYMS/token-based matching above can never see this source phrase
    // at all — check the un-tokenized normalized string directly instead.
    if (qNorm && /(?:^|[^a-z0-9])m\s*&\s*m(?:[^a-z0-9]|$)/.test(qNorm)) add("m&m");
    return out;
  }

  // Returns [{phrase, tok}] for every INTENT target keyword whose intent
  // PHRASE (key) is present in the query. `tok` is diacritics-preserved for
  // the same reason as expandQueryTerms() above.
  function intentTargets(qTokens) {
    const out = [];
    const seen = new Set();
    for (const key of Object.keys(INTENT)) {
      if (phraseContains(qTokens, tokens(key), false)) {
        for (const t of INTENT[key]) {
          const tok = tokensCaseFold(t);
          const k = tok.join(" ");
          if (tok.length && !seen.has(k)) {
            seen.add(k);
            out.push({ phrase: t, tok });
          }
        }
      }
    }
    return out;
  }

  // Returns [{phrase, label, tok}] for every CATEGORY target whose natural
  // browsing phrase (key) is present in the query. `tok` is the no-diacritics
  // token form of the target LABEL, matched against catTokens (which is also
  // no-diacritics — see buildIndex()).
  function categoryTargets(qTokens) {
    const out = [];
    const seen = new Set();
    for (const key of Object.keys(CATEGORY)) {
      if (phraseContains(qTokens, tokens(key), false)) {
        const label = CATEGORY[key];
        const tok = tokens(label);
        const k = tok.join(" ");
        if (tok.length && !seen.has(k)) {
          seen.add(k);
          out.push({ phrase: key, label, tok });
        }
      }
    }
    return out;
  }

  // Rule 5 (BA meeting 2026-08-24): "matching từ nhiều nhất thì hiển thị lên
  // đầu" - a NEW ranking dimension standing ALONGSIDE the tier system (per
  // user: "đứng ngang/trên tier"), not just a same-tier tiebreak. Counts how
  // many DISTINCT query tokens (no-diacritics form) appear anywhere in the
  // product's name/translated-name/category - deliberately NOT descTokens
  // (kept diacritics-strict elsewhere for real collision reasons; mixing
  // strictness levels here would make the count inconsistent). In practice
  // this mostly discriminates WITHIN the weaker bag-style tiers (description/
  // synonym/intent/category/partial), since exact/no_diacritics/multilang/
  // typo/brand all require matching the (near-)full query phrase already, so
  // their count is already at/near the query's own token length - the
  // existing "Tên sản phẩm chính xác > Description > Synonym" priority the
  // user set at the very start of this project is preserved as a natural
  // consequence, not overridden.
  function matchedWordCount(entry, qTokens) {
    if (!qTokens.length) return 0;
    const bag = new Set(entry.nameTokens.concat(entry.nameEnTokens, entry.nameKrTokens, entry.catTokens));
    let n = 0;
    for (const t of new Set(qTokens)) if (bag.has(t)) n++;
    return n;
  }

  // Score one product against a query. Returns {score, tier, note} or null.
  // qTokens/qCaseFoldTokens/qNorm come pre-tokenized from search(); expanded/
  // intents are the outputs of expandQueryTerms()/intentTargets() above.
  function scoreProduct(entry, qCaseFoldTokens, qTokens, qNorm, expanded, intents, allowTypo, categories) {
    let best = null;
    const consider = (score, tier, note) => {
      if (!best || score > best.score) best = { score, tier, note };
    };

    if (phraseContains(entry.nameCaseFoldTokens, qCaseFoldTokens)) {
      consider(100, "exact", "Khớp chính xác trong tên sản phẩm.");
    }
    if (entry.brandTokens.length && phraseContains(entry.brandTokens, qCaseFoldTokens, true)) {
      consider(95, "brand", `Khớp theo thương hiệu sản phẩm: "${entry.brandTokens.join(" ")}".`);
    }
    if (phraseContains(entry.nameTokens, qTokens)) {
      consider(92, "no_diacritics", "Khớp tên sản phẩm sau khi bỏ dấu.");
    }
    if (qTokens.length && qNorm.length >= 3) {
      if (phraseContains(entry.nameEnTokens, qTokens)) consider(88, "multilang", "Khớp tên tiếng Anh đã dịch.");
      if (phraseContains(entry.nameKrTokens, qTokens)) consider(88, "multilang", "Khớp tên tiếng Hàn đã dịch.");
    }
    // fuzzy/typo: tolerates 1 character-level typo (incl. adjacent-key swaps) in
    // any single token of the query, single- or multi-word alike. Gated on
    // allowTypo so candidate-validation callers (glossary/name-fragment
    // keywords, never typos) can skip this — otherwise it re-runs on every
    // postings-superset candidate that missed the higher tiers, which is the
    // single most expensive check in the whole scorer.
    if (!best && allowTypo && qTokens.length && qNorm.length >= 4 && qNorm.length <= 30) {
      if (phraseContainsFuzzy(entry.nameTokens, qTokens, editDistanceLE)) {
        consider(80, "typo", "Khớp qua bước chuẩn hoá & sửa lỗi chính tả (sai lệch tối đa 1 ký tự) với tên sản phẩm.");
      }
    }
    if (entry.descTokens.length && bagContainsAll(entry.descTokens, qCaseFoldTokens)) {
      consider(65, "description", "Khớp từ khoá trong mô tả sản phẩm.");
    }
    for (const alt of expanded) {
      if (phraseContains(entry.nameCaseFoldTokens, alt.tok, false)) {
        consider(60, "synonym", `Khớp qua đồng nghĩa/biến thể vùng miền: "${alt.phrase}".`);
      }
    }
    for (const it of intents) {
      if (phraseContains(entry.nameCaseFoldTokens, it.tok, false)) {
        consider(45, "intent", `Khớp theo mục đích sử dụng (từ khoá liên quan: "${it.phrase}").`);
      } else if (entry.descTokens.length && bagContainsAll(entry.descTokens, tokensCaseFold(it.phrase))) {
        consider(40, "intent", `Khớp theo mục đích sử dụng, tìm thấy trong mô tả (từ khoá liên quan: "${it.phrase}").`);
      }
    }
    if (qTokens.length && qNorm.length >= 3 && phraseContains(entry.catTokens, qTokens)) {
      consider(35, "category", "Khớp theo danh mục sản phẩm (browsing intent).");
    }
    for (const ct of categories) {
      if (phraseContains(entry.catTokens, ct.tok, false)) {
        consider(35, "category", `Khớp theo danh mục liên quan: "${ct.phrase}" → ${ct.label}.`);
      }
    }
    // Last-resort partial match: every tier above requires either a full
    // CONSECUTIVE phrase or a full AND-bag (every query token present). Real
    // multi-word queries routinely combine two unrelated concepts that just
    // happen to sit near each other in the sentence but never appear adjacent
    // in any one product's name — "mua đồ biển" ("đồ"+"biển" not consecutive
    // in "Ghế Ngồi Biển Cả...") is a concrete example: the product genuinely
    // has "biển" in its name (a bare "biển" query finds it at the exact
    // tier), but the 2-word phrase requirement made it invisible, and the
    // query fell through entirely to an unrelated seafood CATEGORY match
    // with nothing surfacing the literal name hit at all. A real BM25-style
    // engine (see OVERVIEW-FLOW-VI_Phase1.pdf) gives partial term-overlap
    // credit instead of an all-or-nothing phrase match. Scored low (20, below
    // category=35). Matches on the NO-DIACRITICS form (qTokens/nameTokens,
    // not the case-fold form) so this safety net also covers no-diacritics
    // queries — a diacritics-preserved version left a no-diacritics query
    // like "sua nhap khau" with ZERO results, since none of its tokens can
    // ever equal an accented catalog token. Common Vietnamese function words
    // (STOPWORDS_VI) are excluded from counting as a match: "cho" (for) alone
    // is >=3 chars and appears in huge numbers of unrelated product names
    // ("...Cho Máy Giặt...") — without this filter, any query containing a
    // stray preposition/conjunction spuriously matched hundreds of products
    // that share nothing with the query's actual subject.
    if (!best && qTokens.length > 1) {
      const matched = qTokens.filter((t) => t.length >= 3 && !STOPWORDS_VI.has(t) && entry.nameTokens.includes(t));
      if (matched.length) {
        consider(20, "partial", `Khớp một phần từ khoá trong tên sản phẩm: "${matched.join(", ")}".`);
      }
    }
    return best;
  }

  // Real users prefix searches with a verb ("mua sữa bột", "tìm giày chạy bộ",
  // "cần mua tã") that never appears in a product name. Since matching is
  // phrase-based (the query must appear as a CONSECUTIVE run), leaving the
  // verb in place means the whole phrase never matches anything — greedily
  // strip a leading run of these before tokenizing, same as a real search box
  // would. Always leaves at least one word behind.
  const LEADING_VERBS_1 = new Set(["mua", "tim", "kiem", "can", "dat", "muon"]);
  const LEADING_VERBS_2 = new Set(["can mua", "dat mua", "muon mua", "tim mua", "can tim", "tim kiem"]);
  function stripLeadingVerbs(raw) {
    const words = raw.split(/\s+/).filter(Boolean);
    if (words.length <= 1) return raw;
    const normWords = words.map((w) => normalize(w));
    let i = 0;
    while (i < words.length - 1) {
      if (i + 2 < words.length && LEADING_VERBS_2.has(normWords[i] + " " + normWords[i + 1])) { i += 2; continue; }
      if (LEADING_VERBS_1.has(normWords[i])) { i += 1; continue; }
      break;
    }
    return i > 0 ? words.slice(i).join(" ") : raw;
  }

  function search(index, query, opts) {
    opts = opts || {};
    const limit = opts.limit || Infinity;
    const raw = stripLeadingVerbs(String(query || "").trim());
    if (!raw) return [];
    const { entries, idxCaseFold, idxNorm, idxNameOnly } = index;
    const qCaseFoldTokens = tokensCaseFold(raw);
    const qTokens = tokens(raw);
    const qNorm = normalize(raw);
    const expanded = expandQueryTerms(qTokens, qCaseFoldTokens, qNorm);
    const intents = intentTargets(qTokens);
    const categories = categoryTargets(qTokens);

    // Candidate narrowing: union of every index-backed match path in
    // scoreProduct() (all safe supersets — see buildIndex() comment above).
    const candidates = new Set();
    for (const i of candidatesForPhrase(idxCaseFold, qCaseFoldTokens, true)) candidates.add(i);
    for (const i of candidatesForPhrase(idxNorm, qTokens, true)) candidates.add(i);
    for (const alt of expanded) for (const i of candidatesForPhrase(idxCaseFold, alt.tok, false)) candidates.add(i);
    for (const it of intents) {
      for (const i of candidatesForPhrase(idxCaseFold, it.tok, false)) candidates.add(i);
      for (const i of candidatesForBag(idxCaseFold, tokensCaseFold(it.phrase))) candidates.add(i);
    }
    for (const ct of categories) for (const i of candidatesForPhrase(idxNorm, ct.tok, false)) candidates.add(i);
    // Union (not intersection) of individual-token postings — candidate feed
    // for the "partial" last-resort tier in scoreProduct(), which needs ANY
    // single matching token considered, not just products matching every
    // token as one consecutive/AND run like the paths above. No-diacritics
    // form (idxNorm/qTokens), matching scoreProduct's partial-tier check, so
    // a no-diacritics query also benefits from this safety net.
    if (qTokens.length > 1) {
      for (const t of qTokens) {
        if (t.length < 3 || STOPWORDS_VI.has(t)) continue;
        const arr = idxNorm.map.get(t);
        if (arr) for (const i of arr) candidates.add(i);
      }
    }

    const results = [];
    const scoredIdx = candidates;
    // Typo-tolerance is now a genuine FALLBACK, not a parallel scoring tier:
    // only computed if the main keyword comes up completely empty first. This
    // matches both the user's explicit rule ("nếu từ khoá chính không khớp
    // mới bắt đầu tìm đến lỗi chính tả") and the real production flow doc's
    // design (spelling-correction only kicks in once the literal search finds
    // nothing) — and it fixes a real quality bug: a query like "cống nghẹt"
    // used to be outranked by a coincidental fuzzy match ("...Công Nghệ...")
    // even when the correct intent-tier match was already present, just
    // because typo was scored unconditionally above synonym/intent.
    let bestMainScore = 0;
    const mainScoreByIdx = new Map();
    for (const i of scoredIdx) {
      const entry = entries[i];
      const m = scoreProduct(entry, qCaseFoldTokens, qTokens, qNorm, expanded, intents, false, categories);
      if (m) {
        results.push({ product: entry.p, score: m.score, tier: m.tier, note: m.note, popularity: entry.popularity,
                       matchedWords: matchedWordCount(entry, qTokens) });
        mainScoreByIdx.set(i, m.score);
        if (m.score > bestMainScore) bestMainScore = m.score;
      }
    }
    // Skipped for internal candidate-validation searches (opts.skipTypo) where
    // candidates are always curated glossary/name-fragment phrases that are
    // guaranteed to be exact-matchable, never typos — and skipped whenever the
    // main keyword already found something CONFIDENT, per the fallback rule
    // above. "confident" excludes a bare "partial" (score 20) hit: that tier
    // is itself a weak last-resort single-token coincidence (e.g. "coa cola"
    // partially matches "cola" literally), so on its own it must not block
    // typo-correction from getting a chance to find the real, better match.
    if (!opts.skipTypo && bestMainScore <= 20 && qTokens.length && qNorm.length >= 4 && qNorm.length <= 30) {
      for (const i of typoCandidates(idxNameOnly, qTokens)) {
        // Only skip a candidate the main pass already scored ABOVE the weak
        // "partial" tier (20) — typo's own score (80) would always beat a
        // bare partial hit, so a partial-only candidate still deserves a
        // chance to be re-scored here (see "coa cola": the real Coca Cola
        // products get pulled in as "partial" via a literal "cola" token
        // overlap, and without this check they'd get stuck at 20 instead of
        // upgrading to the correct typo=80 match).
        const priorScore = mainScoreByIdx.get(i) || 0;
        if (priorScore > 20) continue;
        const entry = entries[i];
        if (phraseContainsFuzzy(entry.nameTokens, qTokens, editDistanceLE)) {
          // If the main pass already gave this same product a "partial" (20)
          // entry, drop it now — typo (80) supersedes it, and both must not
          // coexist in the output as duplicate rows for one product.
          if (priorScore > 0) {
            const dupIdx = results.findIndex((r) => r.product === entry.p);
            if (dupIdx !== -1) results.splice(dupIdx, 1);
          }
          results.push({ product: entry.p, score: 80, tier: "typo", note: "Khớp qua bước chuẩn hoá & sửa lỗi chính tả (sai lệch tối đa 1 ký tự) với tên sản phẩm — chỉ áp dụng vì từ khoá chính không tìm thấy kết quả nào.", popularity: entry.popularity,
                         matchedWords: matchedWordCount(entry, qTokens) });
        }
      }
    }
    // Rule 5: matchedWords ranks ABOVE tier score (see matchedWordCount comment).
    results.sort((a, b) => b.matchedWords - a.matchedWords || b.score - a.score || b.popularity - a.popularity);
    return limit === Infinity ? results : results.slice(0, limit);
  }

  // ---------------------------------------------------------------------
  // Autocomplete: candidate keyword generation + groundedness validation
  // ---------------------------------------------------------------------

  function candidateKeywords(index, query) {
    const raw = stripLeadingVerbs(String(query || "").trim());
    const qTokens = tokens(raw);
    const qCaseFoldTokens = tokensCaseFold(raw);
    const qNorm = normalize(raw);
    const out = new Set();

    // 1) direct matches -> pull short keyword fragments from matched product names
    const direct = search(index, raw, { limit: 60 });
    for (const r of direct) {
      const words = (r.product.name || "").split(/\s+/).filter(Boolean);
      if (words.length) {
        out.add(words.slice(0, Math.min(3, words.length)).join(" "));
      }
      if (words.length > 3) out.add(words.slice(0, 2).join(" "));
    }

    // 2) glossary-driven expansions relevant to the query (exact-phrase gated, see expandQueryTerms)
    for (const alt of expandQueryTerms(qTokens, qCaseFoldTokens, qNorm)) out.add(alt.phrase);
    for (const it of intentTargets(qTokens)) out.add(it.phrase);
    for (const ct of categoryTargets(qTokens)) out.add(ct.label);
    // 2b) intent/category PHRASES themselves as autocomplete-style prefix
    // completions (e.g. typing "gy" should be able to suggest the phrase
    // "gym"), word-boundary safe
    if (qNorm.length >= 2) {
      for (const key of Object.keys(INTENT)) {
        if (phraseContains(tokens(key), qTokens, true)) out.add(key);
      }
      for (const key of Object.keys(CATEGORY)) {
        if (phraseContains(tokens(key), qTokens, true)) out.add(key);
      }
    }

    // 3) category names of matched products (browsing suggestions)
    for (const r of direct.slice(0, 15)) {
      if (r.product.cat) out.add(r.product.cat.toLowerCase());
    }

    return Array.from(out).filter((k) => k && k.length >= 2 && k.length <= 40);
  }

  function autocomplete(index, query, topN) {
    topN = topN || 30;
    const candidates = candidateKeywords(index, query);
    const scored = [];
    for (const kw of candidates) {
      if (isBannedKeyword(kw)) continue; // never shown, independent of groundedness
      const hits = search(index, kw, { limit: 5, skipTypo: true });
      if (hits.length > 0) {
        scored.push({
          keyword: kw,
          verified_product_count: hits.length === 5 ? "5+" : hits.length,
          best_score: hits[0].score,
          popularity: hits[0].popularity,
        });
      }
      // groundedness requirement: if hits.length === 0, candidate is dropped entirely
    }
    scored.sort((a, b) => b.best_score - a.best_score || b.popularity - a.popularity);
    const seen = new Set();
    const out = [];
    for (const s of scored) {
      const key = s.keyword.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(s);
      if (out.length >= topN) break;
    }
    return out;
  }

  // ---------------------------------------------------------------------
  // Adaptive-search route classification — mirrors Phần 2 of the production
  // flow doc (OVERVIEW-FLOW-VI_Phase1.pdf): từ khoá (keyword/BM25) always
  // runs first; its top match's score is read as a 0–100% "độ chắc chắn"
  // and compared against a threshold (production default 50%). Confident
  // enough → stop, keyword-only, never calls AI. Not confident → the real
  // system calls the AI/semantic (embedding) branch and merges both lists
  // via Reciprocal Rank Fusion. This simulator has no live embedding model
  // to call, so the intent/category tiers stand in for "what the AI branch
  // would catch that keyword search alone couldn't" — both score below the
  // threshold by design so this mapping holds. exact/no_diacritics/
  // multilang/typo/description/synonym all represent matches BM25 itself
  // would already find (synonym expansion and translated-field matching
  // both happen inside OpenSearch's keyword analyzer per the doc, not a
  // separate weaker pass), so they stay in the keyword branch.
  // Rule 6 (BA meeting 2026-08-24): "search đúng tên (100% matching) -> chỉ
  // hiện đúng sản phẩm đó + 'Có thể bạn sẽ thích'". Per user confirmation,
  // this reuses the EXACT SAME algorithm already spec'd for the Zero Result
  // page's "Có thể bạn sẽ thích" block (BRD FR-ZR-02 / Storyboard SS-SCR-012,
  // slide 17): Substitute (Vector/Category similarity) -> Cross-sell (Basket
  // Analysis) -> deepest fallback: best-seller. Real NSG catalog data check
  // (2026-08-24): substitute_product_sku is populated on ~82% of SKUs;
  // cross_sell_product_sku and upsell_product_sku are populated on 0% of
  // SKUs (always empty arrays) - kept in the chain anyway per spec, in case
  // that changes or another store's data populates it; in practice today it
  // always falls through to substitute -> best-seller. related_product_sku
  // (7.8% populated) is deliberately NOT used here - FR-ZR-02 does not
  // mention it, so it's out of scope for this specific "Có thể bạn sẽ thích"
  // block (it may back some other feature, e.g. a PDP page, not this one).
  // Literal "results.length === 1" (zero OTHER matches anywhere, at any tier)
  // is unrealistic given the "partial" last-resort tier exists specifically to
  // avoid zero-results by picking up weak single-token overlaps - almost any
  // multi-word query ends up with some trailing partial-tier noise. The
  // business-meaningful reading of "search đúng tên (100% matching)" is: is
  // there exactly ONE unambiguous top exact-tier match (no tie with another
  // exact-tier product) - real UI would still short-circuit to the single-
  // product view even if a few weak, lower-tier matches also technically
  // exist below it.
  function isSingleExactMatch(results) {
    if (!results.length || results[0].tier !== "exact" || results[0].score !== 100) return false;
    return results.length === 1 || results[1].tier !== "exact";
  }

  function pickYouMightLike(index, targetProduct, topN) {
    topN = topN || 10;
    const bySku = new Map();
    for (const e of index.entries) bySku.set(e.p.sku, e.p);
    const out = [];
    const seen = new Set([targetProduct.sku]);
    const addFromSkuList = (skuList, source) => {
      if (!skuList) return;
      for (const sku of skuList) {
        if (out.length >= topN) break;
        if (seen.has(sku)) continue;
        const p = bySku.get(sku);
        if (!p) continue; // not in this store's catalog, or filtered out as inactive
        seen.add(sku);
        out.push({ sku, name: p.name, source });
      }
    };
    addFromSkuList(targetProduct.substitute_product_sku, "substitute");
    addFromSkuList(targetProduct.cross_sell_product_sku, "cross_sell");
    if (out.length < topN) {
      const sameCat = index.entries
        .filter((e) => e.p.cat === targetProduct.cat && !seen.has(e.p.sku))
        .sort((a, b) => b.popularity - a.popularity);
      for (const e of sameCat) {
        if (out.length >= topN) break;
        seen.add(e.p.sku);
        out.push({ sku: e.p.sku, name: e.p.name, source: "best_seller" });
      }
    }
    return out;
  }

  const CONFIDENCE_THRESHOLD = 50;
  const TIER_BRANCH = {
    exact: "keyword", brand: "keyword", no_diacritics: "keyword", multilang: "keyword", typo: "keyword",
    description: "keyword", synonym: "keyword", intent: "ai", category: "ai", partial: "ai",
  };
  function routeFor(results) {
    const confidence = results.length ? results[0].score : 0;
    const route = confidence >= CONFIDENCE_THRESHOLD ? "keyword" : "keyword_ai";
    const routeLabel = route === "keyword"
      ? "Chỉ từ khoá — đủ chắc chắn"
      : "Từ khoá + AI — chưa đủ chắc chắn";
    return { confidence, route, routeLabel };
  }

  return { buildIndex, search, autocomplete, normalize, SYNONYMS, REGIONAL, INTENT, CATEGORY, routeFor, TIER_BRANCH, CONFIDENCE_THRESHOLD, BANNED_WORDS, isBannedKeyword, isActiveProduct, matchedWordCount, isSingleExactMatch, pickYouMightLike };
});
