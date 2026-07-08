package com.example.ui.screens

import android.graphics.Bitmap
import androidx.activity.compose.BackHandler
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.viewinterop.AndroidView
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import java.text.NumberFormat
import java.util.Locale
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.PathMeasure
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.drawscope.rotate as rotateDraw
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.network.OrderRecord
import com.example.ui.viewmodel.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import androidx.compose.ui.graphics.ImageBitmap
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sin

/* ============================================================
 *  CartMe · 디자인 토큰  (image 목업 기반 · 앰버 브랜드)
 *  ※ 변수명은 기존 호환을 위해 유지하되 값만 CartMe 앰버 팔레트로 교체.
 *    Blue = CartMe 노란 브랜드색(버튼/포인트), Navy = 중립 다크 텍스트.
 * ============================================================ */
private val Blue        = Color(0xFFF8C038)   // primary · CartMe 앰버 (버튼/포인트 채움)
private val AmberInk    = Color(0xFFC98A00)   // 밝은 배경 위 앰버 강조 텍스트(대비 확보)
private val BlueSoft    = Color(0xFFFDF1D2)   // 소프트 앰버 칩 배경
private val Navy        = Color(0xFF1E232B)   // 본문 진한 텍스트 (중립 다크)
private val NavyDeep    = Color(0xFF14181D)   // 어두운 화면 배경(페어링/결제완료)
private val ScreenBg    = Color(0xFFF6F0E4)   // 일반 화면 크림 배경
private val Surface     = Color(0xFFFFFFFF)
private val InputBg     = Color(0xFFF6F0E4)
private val InputBorder = Color(0xFFECE3D0)
private val TextSub     = Color(0xFF9A917F)   // 크림 위 보조 텍스트(웜 그레이)
private val TextFaint   = Color(0xFFB4AB98)
private val Green       = Color(0xFF22C55E)
private val OnDarkSub   = Color(0xFFA79E88)   // 다크 배경 위 보조 텍스트
private val LightBlue   = Color(0xFFEADCB9)   // 다크 배경 위 밝은 보조 텍스트
private val Danger      = Color(0xFFE5484D)
private val Line        = Color(0xFFF0EBDD)
private val Cheek       = Color(0xFFFFC2D1)
private val MascotRing  = Color(0xFFBCD7FF)
private val MascotMesh  = Color(0xFFDCEBFF)

private val RBtn   = 18.dp
private val RInput = 16.dp
private val RCard  = 20.dp

private fun won(n: Int): String = NumberFormat.getNumberInstance(Locale.KOREA).format(n)

/* ============================================================
 *  ENTRY
 * ============================================================ */
@Composable
fun CartAppContent(viewModel: CartViewModel, innerPadding: PaddingValues) {
    val uiState by viewModel.uiState.collectAsState()

    // 상태바 영역까지 화면별 배경색이 채워지도록 바깥 Box 배경을 화면에 맞춘다.
    val screenBg = when (uiState.currentScreen) {
        Screen.SPLASH -> Surface                         // 스플래시: 흰 배경 + 노란 원 로고
        Screen.SIGNUP -> Blue                            // 회원가입: 앰버 배경
        Screen.COMPLETION -> NavyDeep                    // 결제완료: 다크 배경
        Screen.LOGIN -> Surface
        Screen.ONBOARDING -> ScreenBg                    // 온보딩: 크림 배경
        Screen.DASHBOARD,                                // QR 페어링: 크림 배경 (목업)
        Screen.SHOPPING, Screen.PAYMENT, Screen.SUPPORT -> ScreenBg
    }

    // 고객센터(챗봇)에서 뒤로가기 눌렀을 때 돌아갈 화면을 기억한다.
    var supportOrigin by remember { mutableStateOf(Screen.SHOPPING) }

    // 챗봇 FAB 를 사용자가 드래그해서 옮긴 위치(px). 대시보드/쇼핑 화면 간 유지된다.
    var fabOffset by remember { mutableStateOf(Offset.Zero) }
    var containerSize by remember { mutableStateOf(IntSize.Zero) }
    var fabSize by remember { mutableStateOf(IntSize.Zero) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(screenBg)
            .padding(innerPadding)
            .onSizeChanged { containerSize = it }
    ) {
        Crossfade(targetState = uiState.currentScreen, label = "screen") { screen ->
            when (screen) {
                Screen.SPLASH -> SplashScreen { viewModel.navigateTo(Screen.LOGIN) }
                Screen.LOGIN -> LoginScreen(
                    errorMessage = uiState.errorMessage,
                    isLoading = uiState.isLoading,
                    onLogin = { email, pw -> viewModel.login(email, pw) },
                    onSignUp = { viewModel.navigateTo(Screen.SIGNUP) }
                )
                Screen.SIGNUP -> SignUpScreen(
                    errorMessage = uiState.errorMessage,
                    isLoading = uiState.isLoading,
                    onSubmit = { n, p, email, pw -> viewModel.signUp(n, p, email, pw) },
                    onBack = { viewModel.navigateTo(Screen.LOGIN) }
                )
                Screen.ONBOARDING -> OnboardingScreen(
                    onFinish = { viewModel.navigateTo(Screen.DASHBOARD) }
                )
                Screen.DASHBOARD -> {
                    LaunchedEffect(Unit) { viewModel.generateQR() }
                    PairScreen(
                        uiState = uiState,
                        onGenerateQR = { viewModel.generateQR() },
                        onLogout = { viewModel.logout() },
                        onFetchHistory = { viewModel.fetchOrderHistory() }
                    )
                }
                Screen.SHOPPING -> ShoppingScreen(
                    uiState = uiState,
                    viewModel = viewModel,
                    onCheckout = { viewModel.navigateTo(Screen.PAYMENT) }
                )
                Screen.PAYMENT -> PaymentScreen(
                    uiState = uiState,
                    isLoading = uiState.isLoading,
                    errorMessage = uiState.errorMessage,
                    onPay = { viewModel.completeOrder() },
                    onBack = { viewModel.navigateTo(Screen.SHOPPING) }
                )
                Screen.COMPLETION -> CompletionScreen(
                    uiState = uiState,
                    onRestart = { viewModel.logout() }
                )
                Screen.SUPPORT -> SupportScreen(
                    token = uiState.token,
                    userName = uiState.userName,
                    onBack = { viewModel.navigateTo(supportOrigin) }
                )
            }
        }

        if (uiState.currentScreen == Screen.DASHBOARD || uiState.currentScreen == Screen.SHOPPING) {
            VoiceToast(
                message = uiState.latestVoiceGuidance,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(start = 16.dp, end = 16.dp, bottom = 16.dp)
            )

            // 오른쪽 아래 떠 있는 챗봇(고객센터) 버튼
            // SHOPPING 은 하단 결제 시트가 있어 조금 더 위로 띄운다.
            val fabBottom = if (uiState.currentScreen == Screen.SHOPPING) 168.dp else 28.dp
            ChatbotFab(
                onClick = {
                    supportOrigin = uiState.currentScreen
                    viewModel.navigateTo(Screen.SUPPORT)
                },
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    // 사용자가 끌어서 옮긴 만큼 위치 이동
                    .offset { IntOffset(fabOffset.x.roundToInt(), fabOffset.y.roundToInt()) }
                    .onSizeChanged { fabSize = it }
                    .pointerInput(containerSize, fabSize) {
                        detectDragGestures { change, drag ->
                            change.consume()
                            // BottomEnd 기준이라 x/y 음수 = 왼쪽/위로 이동. 화면 밖으로 나가지 않도록 clamp.
                            val minX = -(containerSize.width - fabSize.width).toFloat().coerceAtLeast(0f)
                            val minY = -(containerSize.height - fabSize.height).toFloat().coerceAtLeast(0f)
                            fabOffset = Offset(
                                (fabOffset.x + drag.x).coerceIn(minX, 0f),
                                (fabOffset.y + drag.y).coerceIn(minY, 0f),
                            )
                        }
                    }
                    .padding(end = 20.dp, bottom = fabBottom)
            )
        }
    }
}

/* ============================================================
 *  챗봇 FAB — 오른쪽 아래 떠 있는 고객센터 런처
 *  (Channel.io / 인터콤 스타일의 상담 위젯 pill)
 * ============================================================ */
@Composable
private fun ChatbotFab(onClick: () -> Unit, modifier: Modifier = Modifier) {
    // 은은하게 위아래로 떠오르는 모션
    val t = rememberInfiniteTransition(label = "fab")
    val floatY by t.animateFloat(
        initialValue = 0f, targetValue = -5f,
        animationSpec = infiniteRepeatable(tween(1800, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "fabFloat"
    )
    Row(
        modifier = modifier
            .offset(y = floatY.dp)
            .shadow(20.dp, RoundedCornerShape(32.dp), ambientColor = Blue, spotColor = Blue.copy(alpha = 0.5f))
            .clip(RoundedCornerShape(32.dp))
            .background(Surface)
            .border(1.5.dp, Navy, RoundedCornerShape(32.dp))
            .clickable { onClick() }
            .padding(start = 7.dp, end = 18.dp, top = 7.dp, bottom = 7.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // 마스코트 아바타 + 온라인 표시
        Box(
            Modifier.size(46.dp).clip(CircleShape)
                .background(Brush.linearGradient(listOf(Blue, TutBlueDeep))),
            contentAlignment = Alignment.Center
        ) {
            Mascot(width = 32.dp, mood = "wave", onLight = true)
        }
        Spacer(Modifier.width(11.dp))
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("도움 챗봇", fontSize = 14.5.sp, fontWeight = FontWeight.ExtraBold, color = Navy)
                Spacer(Modifier.width(5.dp))
                Text("🛒", fontSize = 12.sp)
            }
            Text("무엇이든 물어보세요", fontSize = 11.5.sp, fontWeight = FontWeight.Medium, color = TextSub,
                modifier = Modifier.padding(top = 1.dp))
        }
    }
}

/* ============================================================
 *  SUPPORT — 고객센터 챗봇 (WebView 로 chatbot.html 로드)
 * ============================================================ */
@Composable
private fun SupportScreen(token: String, userName: String, onBack: () -> Unit) {
    // 안드로이드 물리 뒤로가기도 이전 화면으로
    BackHandler(onBack = onBack)

    // 챗봇 WebView 가 '문의하기'를 백엔드로 전송할 수 있도록 base/token/name 전달
    val chatUrl = remember(token, userName) {
        fun enc(s: String) = java.net.URLEncoder.encode(s, "UTF-8")
        "file:///android_asset/chatbot.html" +
            "?base=" + enc(com.example.network.RetrofitClient.BASE_URL) +
            "&token=" + enc(token) +
            "&name=" + enc(userName)
    }

    // enableEdgeToEdge 환경에선 adjustResize 가 무시되므로 imePadding 으로
    // 키보드 높이만큼 화면을 줄여야 하단 문의 입력창이 키보드에 가려지지 않는다.
    Column(Modifier.fillMaxSize().background(ScreenBg).imePadding()) {
        // 상단 바
        Row(
            modifier = Modifier.fillMaxWidth().background(Surface)
                .padding(start = 12.dp, end = 20.dp, top = 12.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).clickable { onBack() },
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Filled.ArrowBack, contentDescription = "뒤로", tint = Navy, modifier = Modifier.size(22.dp))
            }
            Spacer(Modifier.width(4.dp))
            Text("고객센터", fontSize = 22.sp, fontWeight = FontWeight.Black, color = Navy)
        }
        Divider(color = Line, thickness = 1.dp)

        // 챗봇 WebView — Column 에서 남은 공간만 채우도록 weight 사용
        // (fillMaxSize 를 쓰면 상단 바 높이만큼 아래로 밀려 채팅/입력창이 화면 밖으로 잘린다)
        AndroidView(
            modifier = Modifier.fillMaxWidth().weight(1f),
            factory = { ctx ->
                android.webkit.WebView(ctx).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    settings.allowFileAccess = true
                    settings.useWideViewPort = false
                    settings.loadWithOverviewMode = false
                    // file:// 페이지에서 백엔드(http://10.0.2.2:3000)로 fetch 허용
                    @Suppress("DEPRECATION")
                    settings.allowUniversalAccessFromFileURLs = true
                    webViewClient = android.webkit.WebViewClient()
                    setBackgroundColor(android.graphics.Color.parseColor("#F4F6FB"))
                    loadUrl(chatUrl)
                }
            }
        )
    }
}

/* ============================================================
 *  Mascot — 장바구니 캐릭터 (Canvas, CartMe.dc.html Mascot 재현)
 *  mood: "wave" | "idle" | "celebrate"
 * ============================================================ */
@Composable
private fun Mascot(
    width: Dp,
    mood: String = "wave",
    ring: Color = MascotRing,
    mesh: Color = MascotMesh,
    onLight: Boolean = false,   // 밝은 배경 = 원본(검은 라인), 어두운/파란 배경 = 흰색 반전
) {
    // 마스코트는 a1.png 원본 이미지를 그대로 사용한다 (형태 수정 없음).
    // 어두운/파란 배경에서는 선이 안 보이므로 색만 흰색으로 반전한다 (모양 동일).
    // ring / mesh / mood 는 호출부 호환을 위해 남겨두지만 사용하지 않는다.
    val floatT = rememberInfiniteTransition(label = "mascotFloat")
    val dy by floatT.animateFloat(
        initialValue = 0f, targetValue = -7f,
        animationSpec = infiniteRepeatable(tween(1400, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "dy"
    )
    androidx.compose.foundation.Image(
        painter = androidx.compose.ui.res.painterResource(id = com.example.R.drawable.mascot),
        contentDescription = "마스코트",
        colorFilter = if (onLight) null
                      else androidx.compose.ui.graphics.ColorFilter.tint(Color.White),
        modifier = Modifier.size(width).offset(y = dy.dp)
    )
}

/* ============================================================
 *  QR 코드 이미지 (ZXing core → Bitmap → Compose Image)
 * ============================================================ */
@Composable
private fun QrCodeImage(content: String, size: Dp = 180.dp) {
    val density = LocalDensity.current
    val sizePx  = with(density) { size.roundToPx() }

    val bitmap: ImageBitmap? = remember(content) {
        if (content.isBlank()) return@remember null
        try {
            val writer    = QRCodeWriter()
            val bitMatrix = writer.encode(content, BarcodeFormat.QR_CODE, sizePx, sizePx)
            val bmp = Bitmap.createBitmap(sizePx, sizePx, Bitmap.Config.RGB_565)
            for (x in 0 until sizePx) {
                for (y in 0 until sizePx) {
                    bmp.setPixel(x, y, if (bitMatrix[x, y]) android.graphics.Color.parseColor("#16224A")
                                        else android.graphics.Color.WHITE)
                }
            }
            bmp.asImageBitmap()
        } catch (e: Exception) { null }
    }

    if (bitmap != null) {
        androidx.compose.foundation.Image(
            bitmap = bitmap,
            contentDescription = "QR Code",
            modifier = Modifier.size(size)
        )
    } else {
        Box(
            modifier = Modifier.size(size).border(2.dp, InputBorder, RoundedCornerShape(RInput)),
            contentAlignment = Alignment.Center
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Filled.QrCode, contentDescription = null, tint = TextFaint, modifier = Modifier.size(48.dp))
                Spacer(Modifier.height(8.dp))
                Text("버튼을 눌러 QR 생성", fontSize = 12.sp, color = TextFaint)
            }
        }
    }
}

/* ============================================================
 *  공용 컴포넌트
 * ============================================================ */
private enum class BtnVariant { Filled, Outline, Light }

@Composable
private fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    leadingIcon: ImageVector? = null,
    variant: BtnVariant = BtnVariant.Filled,
    height: Dp = 58.dp,
) {
    val container: Color; val content: Color
    when (variant) {
        BtnVariant.Filled  -> { container = Blue;    content = Navy }        // 앰버 버튼 + 다크 텍스트
        BtnVariant.Outline -> { container = Surface; content = Navy }        // 흰 버튼 + 다크 테두리
        BtnVariant.Light   -> { container = Color.White; content = Navy }
    }
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(height),
        shape = RoundedCornerShape(RBtn),
        elevation = if (variant == BtnVariant.Filled)
            ButtonDefaults.buttonElevation(defaultElevation = 8.dp, pressedElevation = 2.dp) else null,
        // 목업(네오브루탈) 스타일 — 버튼에 진한 윤곽선
        border = androidx.compose.foundation.BorderStroke(
            2.dp, if (enabled) Navy else Color(0xFFD8CFBB)),
        colors = ButtonDefaults.buttonColors(
            containerColor = container,
            contentColor = content,
            disabledContainerColor = Color(0xFFEFE1BC),
            disabledContentColor = Color(0xFFB1A277)
        )
    ) {
        if (leadingIcon != null) {
            Icon(leadingIcon, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
    }
}

@Composable
private fun AppInput(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    password: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier.fillMaxWidth().height(58.dp),
        singleLine = true,
        shape = RoundedCornerShape(RInput),
        placeholder = { Text(placeholder, color = TextFaint, fontSize = 15.sp) },
        textStyle = androidx.compose.ui.text.TextStyle(
            fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Navy
        ),
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Blue,
            unfocusedBorderColor = InputBorder,
            focusedContainerColor = InputBg,
            unfocusedContainerColor = InputBg,
            cursorColor = Blue,
        )
    )
}

@Composable
private fun PulsingDot(color: Color, size: Int = 9) {
    val t = rememberInfiniteTransition(label = "dot")
    val a by t.animateFloat(
        initialValue = 1f, targetValue = 2.6f,
        animationSpec = infiniteRepeatable(tween(1600, easing = LinearEasing), RepeatMode.Restart),
        label = "scale"
    )
    Box(contentAlignment = Alignment.Center, modifier = Modifier.size((size + 8).dp)) {
        Canvas(Modifier.size(size.dp)) {
            drawCircle(color = color.copy(alpha = (1.6f - a / 2.6f).coerceIn(0f, 1f) * 0.6f),
                radius = this.size.minDimension / 2 * a)
            drawCircle(color = color, radius = this.size.minDimension / 2)
        }
    }
}

@Composable
private fun VoiceToast(message: String, modifier: Modifier = Modifier) {
    AnimatedVisibility(
        visible = message.isNotBlank(),
        enter = fadeIn() + slideInVertically { it / 2 },
        exit = fadeOut(),
        modifier = modifier
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(RInput)).background(Navy).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(modifier = Modifier.size(30.dp).clip(RoundedCornerShape(9.dp)).background(Blue),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.VolumeUp, contentDescription = null, tint = Navy, modifier = Modifier.size(17.dp))
            }
            Spacer(Modifier.width(11.dp))
            Text(message, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium, lineHeight = 18.sp)
        }
    }
}

@Composable
private fun LogoutChip(onClick: () -> Unit, onDark: Boolean = false) {
    Box(
        modifier = Modifier.size(40.dp).clip(RoundedCornerShape(12.dp))
            .background(if (onDark) Color.White.copy(alpha = 0.14f) else Surface)
            .then(if (onDark) Modifier else Modifier.border(1.5.dp, Navy, RoundedCornerShape(12.dp)))
            .clickable { onClick() },
        contentAlignment = Alignment.Center
    ) {
        Icon(Icons.Filled.ExitToApp, contentDescription = "로그아웃",
            tint = if (onDark) Color.White else Navy, modifier = Modifier.size(19.dp))
    }
}

/* ============================================================
 *  ONBOARDING — 회원가입 직후 튜토리얼 (CartMe 튜토리얼2 · 4단계)
 *    QR 스캔 → 정면/후면 촬영 → 인식·추종 → 결제·복귀
 *    좌우로 스크롤(스와이프)하면 각 단계가 페이드로 전환된다.
 * ============================================================ */
private val DotIdle = Color(0xFFD8CFBB)

// 튜토리얼 일러스트 전용 팔레트 (CartMe 앰버 기반)
private val TutBlue     = Color(0xFFF8C038)   // 일러스트 기본 앰버
private val TutBlueDeep = Color(0xFFE0A100)   // 앰버 음영
private val TutMint     = Color(0xFF28C386)   // 스캔 빔 · 완료 체크
private val TutMarkerBg = Color(0xFFFDF1D2)   // 사용자/홈 마커 배경(소프트 앰버)
private val TutFinder   = Color(0xFFE7DCC4)   // 뷰파인더 테두리(웜)
private val TutVoice    = Color(0xFFFFD98A)   // 음성 안내 포인트(라이트 앰버)
private val TutSkin     = Color(0xFFF4C9A8)
private val TutSkinDark = Color(0xFFEAB892)
private val TutHair     = Color(0xFF3A4661)
private val TutHairDark = Color(0xFF2F3A52)
private val TutFace     = Color(0xFF1E232B)

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun OnboardingScreen(onFinish: () -> Unit) {
    val pageCount = 4
    val pagerState = rememberPagerState(pageCount = { pageCount })
    val scope = rememberCoroutineScope()
    val isLast = pagerState.currentPage == pageCount - 1

    // 첫 진입 힌트: 한 번이라도 스크롤하면 사라진다.
    var hintDismissed by remember { mutableStateOf(false) }
    LaunchedEffect(pagerState) {
        snapshotFlow { pagerState.currentPageOffsetFraction }
            .collect { if (abs(it) > 0.02f) hintDismissed = true }
    }

    Box(Modifier.fillMaxSize().background(ScreenBg)) {
        Column(Modifier.fillMaxSize()) {
            // 상단 바 · 진행 점 + 건너뛰기
            Box(Modifier.fillMaxWidth().height(52.dp).padding(horizontal = 12.dp)) {
                Row(
                    Modifier.align(Alignment.Center),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    repeat(pageCount) { i ->
                        val selected = pagerState.currentPage == i
                        val w by animateDpAsState(if (selected) 22.dp else 7.dp, label = "dotW")
                        Box(
                            Modifier
                                .padding(horizontal = 3.dp)
                                .height(6.dp).width(w)
                                .clip(CircleShape)
                                .background(if (selected) TutBlue else DotIdle)
                        )
                    }
                }
                androidx.compose.animation.AnimatedVisibility(
                    visible = !isLast,
                    enter = fadeIn(), exit = fadeOut(),
                    modifier = Modifier.align(Alignment.CenterEnd)
                ) {
                    Text(
                        "건너뛰기",
                        fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = TextSub,
                        modifier = Modifier
                            .clip(RoundedCornerShape(12.dp))
                            .clickable { onFinish() }
                            .padding(horizontal = 10.dp, vertical = 8.dp)
                    )
                }
            }

            // 스크롤 연동 페이저
            HorizontalPager(
                state = pagerState,
                modifier = Modifier.weight(1f),
            ) { page ->
                val offset = (pagerState.currentPage - page) + pagerState.currentPageOffsetFraction
                val active = page == pagerState.settledPage
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .graphicsLayer {
                            // 위치에 따라 부드럽게 페이드 + 살짝 축소
                            val a = (1f - abs(offset)).coerceIn(0f, 1f)
                            alpha = a
                            val s = 0.92f + 0.08f * a
                            scaleX = s; scaleY = s
                        }
                ) {
                    when (page) {
                        0 -> OnbStepScan(active)
                        1 -> OnbStepCapture(active)
                        2 -> OnbStepFollow(active)
                        else -> OnbStepPay(active)
                    }
                }
            }

            // 다음 / 시작하기 (마지막 단계는 네이비)
            val btnColor by animateColorAsState(if (isLast) TutFace else TutBlue, label = "btnColor")
            Box(
                Modifier
                    .padding(start = 26.dp, end = 26.dp, top = 6.dp, bottom = 28.dp)
                    .fillMaxWidth().height(54.dp)
                    .shadow(10.dp, RoundedCornerShape(16.dp), spotColor = btnColor.copy(alpha = 0.6f))
                    .clip(RoundedCornerShape(16.dp))
                    .background(btnColor)
                    .clickable {
                        if (isLast) onFinish()
                        else scope.launch { pagerState.animateScrollToPage(pagerState.currentPage + 1) }
                    },
                contentAlignment = Alignment.Center
            ) {
                Text(
                    if (isLast) "시작하기" else "다음",
                    color = if (isLast) Color.White else Navy, fontSize = 16.sp, fontWeight = FontWeight.Bold
                )
            }
        }

        // 첫 진입 힌트
        androidx.compose.animation.AnimatedVisibility(
            visible = !hintDismissed,
            enter = fadeIn(), exit = fadeOut(),
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 132.dp)
        ) {
            Row(
                Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(BlueSoft)
                    .padding(horizontal = 14.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                val hintT = rememberInfiniteTransition(label = "hint")
                val dx by hintT.animateFloat(
                    initialValue = -3f, targetValue = 3f,
                    animationSpec = infiniteRepeatable(tween(800, easing = FastOutSlowInEasing), RepeatMode.Reverse),
                    label = "hintDx"
                )
                Icon(Icons.Filled.SwipeLeft, contentDescription = null, tint = AmberInk,
                    modifier = Modifier.size(16.dp).offset(x = dx.dp))
                Spacer(Modifier.width(6.dp))
                Text("스크롤해서 둘러보기", fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = AmberInk)
            }
        }
    }
}

@Composable
private fun OnbStepFrame(
    title: String,
    desc: String,
    art: @Composable BoxScope.() -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize().padding(horizontal = 28.dp)) {
        Spacer(Modifier.height(8.dp))
        Text(title, fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, color = TutFace,
            lineHeight = 34.sp, letterSpacing = (-0.5).sp)
        Spacer(Modifier.height(12.dp))
        Text(desc, fontSize = 14.5.sp, fontWeight = FontWeight.Medium, color = TextSub,
            lineHeight = 22.sp)
        Box(Modifier.weight(1f).fillMaxWidth().padding(top = 8.dp, bottom = 10.dp), content = art)
    }
}

/* 1단계 — 키오스크 QR 스캔: 미니 폰 목업 위로 스캔 빔이 훑고, 끝나면 체크 팝업 */
@Composable
private fun OnbStepScan(active: Boolean) {
    var done by remember { mutableStateOf(false) }
    LaunchedEffect(active) {
        if (active) { done = false; delay(2400); done = true } else done = false
    }
    val scanT = rememberInfiniteTransition(label = "scan")
    val sweep by scanT.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1400, easing = FastOutSlowInEasing), RepeatMode.Restart),
        label = "sweep"
    )
    val checkScale by animateFloatAsState(
        targetValue = if (done) 1f else 0f,
        animationSpec = spring(dampingRatio = 0.5f, stiffness = Spring.StiffnessLow), label = "checkScale"
    )

    OnbStepFrame(
        title = "키오스크에\nQR을 스캔해요",
        desc = "키오스크 카메라에 QR을 비추면\n카트가 배정돼요",
    ) {
        // CartMe 앱 QR 화면 미니 폰 목업
        Column(
            Modifier.align(Alignment.TopCenter).padding(top = 26.dp)
                .width(160.dp)
                .shadow(18.dp, RoundedCornerShape(22.dp), spotColor = TutBlue.copy(alpha = 0.35f))
                .clip(RoundedCornerShape(22.dp))
                .background(Surface)
                .border(1.dp, InputBorder, RoundedCornerShape(22.dp))
        ) {
            Box(
                Modifier.fillMaxWidth().height(32.dp).background(TutBlue),
                contentAlignment = Alignment.Center
            ) {
                Text("CartMe", color = Navy, fontSize = 11.sp, fontWeight = FontWeight.Bold)
            }
            Box(
                Modifier.fillMaxWidth().padding(vertical = 18.dp),
                contentAlignment = Alignment.Center
            ) {
                QrCodeImage(content = "CARTME-PAIR-ONBOARDING", size = 108.dp)
                // 스캔 빔
                Column(
                    Modifier.fillMaxWidth().padding(horizontal = 10.dp)
                        .offset(y = (sweep * 90f - 45f).dp)
                        .alpha(if (done) 0f else 1f)
                ) {
                    Box(
                        Modifier.fillMaxWidth().height(30.dp)
                            .background(Brush.verticalGradient(listOf(
                                TutMint.copy(alpha = 0f), TutMint.copy(alpha = 0.45f))))
                    )
                    Box(Modifier.fillMaxWidth().height(2.5.dp).clip(CircleShape).background(TutMint))
                }
            }
        }
        // 배정 완료 체크
        Box(
            Modifier.align(Alignment.TopCenter).padding(top = 96.dp)
                .size(56.dp).scale(checkScale)
                .shadow(12.dp, CircleShape, spotColor = TutMint.copy(alpha = 0.6f))
                .clip(CircleShape).background(TutMint),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Filled.Check, contentDescription = null, tint = Color.White,
                modifier = Modifier.size(30.dp))
        }
        // 마스코트 (왼쪽 아래에서 빼꼼)
        Box(Modifier.align(Alignment.BottomStart)) {
            Mascot(width = 128.dp, mood = "idle", onLight = true)
        }
    }
}

/* 2단계 — 정면/후면 촬영: 음성 안내 칩 + 뷰파인더에서 정면→플래시→후면→플래시 */
@Composable
private fun OnbStepCapture(active: Boolean) {
    var frontDone by remember { mutableStateOf(false) }
    var backDone  by remember { mutableStateOf(false) }
    var showBack  by remember { mutableStateOf(false) }
    val flash = remember { Animatable(0f) }
    LaunchedEffect(active) {
        frontDone = false; backDone = false; showBack = false; flash.snapTo(0f)
        if (active) {
            delay(1500)
            flash.snapTo(1f); frontDone = true; flash.animateTo(0f, tween(400))
            delay(350)
            showBack = true
            delay(1500)
            flash.snapTo(1f); backDone = true; flash.animateTo(0f, tween(400))
        }
    }
    val toBack by animateFloatAsState(
        targetValue = if (showBack) 1f else 0f,
        animationSpec = tween(550, easing = FastOutSlowInEasing), label = "toBack"
    )
    // 음성 안내 웨이브 바
    val waveT = rememberInfiniteTransition(label = "wave")
    val wavePhase by waveT.animateFloat(
        initialValue = 0f, targetValue = (2 * Math.PI).toFloat(),
        animationSpec = infiniteRepeatable(tween(900, easing = LinearEasing), RepeatMode.Restart),
        label = "wavePhase"
    )

    OnbStepFrame(
        title = "정면과 후면을\n차례로 촬영해요",
        desc = "안내 음성에 따라 몸을 돌리면\n로봇이 나를 정확히 기억해요",
    ) {
        // 음성 안내 칩
        Row(
            Modifier.align(Alignment.TopCenter)
                .shadow(8.dp, RoundedCornerShape(999.dp), spotColor = TutFace.copy(alpha = 0.4f))
                .clip(RoundedCornerShape(999.dp))
                .background(TutFace)
                .padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(Icons.Filled.Mic, contentDescription = null, tint = TutVoice,
                modifier = Modifier.size(14.dp))
            Spacer(Modifier.width(6.dp))
            Text(
                if (toBack < 0.5f) "\"정면을 바라봐 주세요\"" else "\"뒤로 돌아봐 주세요\"",
                fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = Color.White
            )
            Spacer(Modifier.width(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                repeat(4) { i ->
                    val h = 5f + (sin(wavePhase + i * 1.3f) * 0.5f + 0.5f) * 9f
                    Box(
                        Modifier.padding(horizontal = 1.2.dp)
                            .width(3.dp).height(h.dp)
                            .clip(CircleShape).background(TutVoice)
                    )
                }
            }
        }

        // 카메라 뷰파인더
        Box(
            Modifier.align(Alignment.TopCenter).padding(top = 48.dp)
                .width(190.dp).height(220.dp)
                .clip(RoundedCornerShape(26.dp))
                .background(Brush.linearGradient(listOf(Color(0xFFFBF7EE), Color(0xFFF1E9D8))))
                .border(2.dp, TutFinder, RoundedCornerShape(26.dp))
        ) {
            // 인물 (정면 ↔ 후면 플립)
            PersonFront(
                Modifier.align(Alignment.BottomCenter)
                    .width(118.dp).height(148.dp)
                    .graphicsLayer {
                        alpha = 1f - toBack
                        scaleX = (1f - toBack).coerceAtLeast(0.02f)
                    }
            )
            PersonBack(
                Modifier.align(Alignment.BottomCenter)
                    .width(118.dp).height(148.dp)
                    .graphicsLayer {
                        alpha = toBack
                        scaleX = toBack.coerceAtLeast(0.02f)
                    }
            )
            // 회전 힌트
            Icon(
                Icons.Filled.Refresh, contentDescription = null, tint = TutBlue,
                modifier = Modifier.align(Alignment.TopCenter).padding(top = 12.dp)
                    .size(22.dp)
                    .alpha(if (toBack > 0.05f && toBack < 0.95f) 1f else 0f)
            )
            // 코너 브래킷
            ViewfinderCorners(Modifier.matchParentSize())
            // 셔터 플래시
            Box(Modifier.matchParentSize().alpha(flash.value).background(Color.White))
        }

        // 촬영 썸네일 (정면 · 후면)
        Row(
            Modifier.align(Alignment.BottomCenter),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            CaptureThumb(done = frontDone)
            CaptureThumb(done = backDone)
        }
    }
}

@Composable
private fun ViewfinderCorners(modifier: Modifier) {
    Canvas(modifier) {
        val len = 24.dp.toPx()
        val w = 3.dp.toPx()
        val pad = 12.dp.toPx()
        fun corner(ox: Float, oy: Float, dx: Int, dy: Int) {
            drawLine(TutBlue, Offset(ox, oy), Offset(ox + dx * len, oy), strokeWidth = w, cap = StrokeCap.Round)
            drawLine(TutBlue, Offset(ox, oy), Offset(ox, oy + dy * len), strokeWidth = w, cap = StrokeCap.Round)
        }
        corner(pad, pad, 1, 1)
        corner(size.width - pad, pad, -1, 1)
        corner(pad, size.height - pad, 1, -1)
        corner(size.width - pad, size.height - pad, -1, -1)
    }
}

@Composable
private fun CaptureThumb(done: Boolean) {
    val a by animateFloatAsState(if (done) 1f else 0.5f, label = "thumbA")
    Box(
        Modifier.alpha(a).size(40.dp, 48.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(Color(0xFFFBF7EE))
            .border(2.dp, Color(0xFFE7DCC4), RoundedCornerShape(9.dp)),
        contentAlignment = Alignment.Center
    ) {
        if (done) {
            Icon(Icons.Filled.Check, contentDescription = null, tint = TutMint,
                modifier = Modifier.size(18.dp))
        }
    }
}

/* 뷰파인더 속 인물 일러스트 — 정면 (튜토리얼2 SVG 좌표계 120×150 포팅) */
@Composable
private fun PersonFront(modifier: Modifier) {
    Canvas(modifier) {
        val s = size.width / 120f
        fun p(block: Path.() -> Unit) = Path().apply(block)
        // 상의
        drawPath(p {
            moveTo(22f * s, 150f * s)
            cubicTo(22f * s, 112f * s, 36f * s, 92f * s, 44f * s, 88f * s)
            lineTo(76f * s, 88f * s)
            cubicTo(84f * s, 92f * s, 98f * s, 112f * s, 98f * s, 150f * s)
            close()
        }, TutBlue)
        drawPath(p {
            moveTo(44f * s, 88f * s)
            cubicTo(48f * s, 100f * s, 72f * s, 100f * s, 76f * s, 88f * s)
            lineTo(76f * s, 84f * s); lineTo(44f * s, 84f * s); close()
        }, TutBlueDeep)
        // 카라
        drawPath(p {
            moveTo(50f * s, 86f * s); lineTo(60f * s, 96f * s); lineTo(70f * s, 86f * s)
        }, TutBlueDeep, style = Stroke(width = 3f * s, cap = StrokeCap.Round))
        // 목
        drawPath(p {
            moveTo(52f * s, 78f * s); lineTo(52f * s, 90f * s)
            quadraticBezierTo(60f * s, 96f * s, 68f * s, 90f * s)
            lineTo(68f * s, 78f * s); close()
        }, TutSkinDark)
        // 얼굴 · 귀
        drawOval(TutSkinDark, topLeft = Offset(33.5f * s, 48f * s), size = Size(9f * s, 12f * s))
        drawOval(TutSkinDark, topLeft = Offset(77.5f * s, 48f * s), size = Size(9f * s, 12f * s))
        drawOval(TutSkin, topLeft = Offset(37f * s, 27f * s), size = Size(46f * s, 50f * s))
        // 머리카락
        drawPath(p {
            moveTo(35f * s, 52f * s)
            cubicTo(33f * s, 30f * s, 48f * s, 22f * s, 60f * s, 22f * s)
            cubicTo(72f * s, 22f * s, 87f * s, 30f * s, 85f * s, 52f * s)
            cubicTo(85f * s, 44f * s, 80f * s, 38f * s, 72f * s, 37f * s)
            cubicTo(66f * s, 32f * s, 54f * s, 32f * s, 48f * s, 37f * s)
            cubicTo(40f * s, 38f * s, 35f * s, 44f * s, 35f * s, 52f * s)
            close()
        }, TutHair)
        // 눈썹
        drawPath(p {
            moveTo(47f * s, 47f * s); quadraticBezierTo(52f * s, 45f * s, 57f * s, 47f * s)
        }, TutHair, style = Stroke(width = 2f * s, cap = StrokeCap.Round))
        drawPath(p {
            moveTo(63f * s, 47f * s); quadraticBezierTo(68f * s, 45f * s, 73f * s, 47f * s)
        }, TutHair, style = Stroke(width = 2f * s, cap = StrokeCap.Round))
        // 눈
        drawCircle(TutFace, radius = 3.4f * s, center = Offset(52f * s, 53f * s))
        drawCircle(TutFace, radius = 3.4f * s, center = Offset(68f * s, 53f * s))
        drawCircle(Color.White, radius = 1f * s, center = Offset(53.1f * s, 52f * s))
        drawCircle(Color.White, radius = 1f * s, center = Offset(69.1f * s, 52f * s))
        // 볼터치
        drawOval(Color(0xFFF4A9A0).copy(alpha = 0.55f), topLeft = Offset(42f * s, 57.4f * s), size = Size(8f * s, 5.2f * s))
        drawOval(Color(0xFFF4A9A0).copy(alpha = 0.55f), topLeft = Offset(70f * s, 57.4f * s), size = Size(8f * s, 5.2f * s))
        // 미소
        drawPath(p {
            moveTo(53f * s, 63f * s); quadraticBezierTo(60f * s, 69f * s, 67f * s, 63f * s)
        }, TutFace, style = Stroke(width = 2.4f * s, cap = StrokeCap.Round))
    }
}

/* 뷰파인더 속 인물 일러스트 — 후면 */
@Composable
private fun PersonBack(modifier: Modifier) {
    Canvas(modifier) {
        val s = size.width / 120f
        fun p(block: Path.() -> Unit) = Path().apply(block)
        // 상의 뒷면
        drawPath(p {
            moveTo(22f * s, 150f * s)
            cubicTo(22f * s, 112f * s, 36f * s, 92f * s, 44f * s, 88f * s)
            lineTo(76f * s, 88f * s)
            cubicTo(84f * s, 92f * s, 98f * s, 112f * s, 98f * s, 150f * s)
            close()
        }, TutBlueDeep)
        drawPath(p {
            moveTo(44f * s, 88f * s)
            cubicTo(48f * s, 96f * s, 72f * s, 96f * s, 76f * s, 88f * s)
            lineTo(76f * s, 84f * s); lineTo(44f * s, 84f * s); close()
        }, Color(0xFF1F52C0))
        drawPath(p {
            moveTo(50f * s, 87f * s); quadraticBezierTo(60f * s, 92f * s, 70f * s, 87f * s)
        }, Color(0xFF1F52C0), style = Stroke(width = 3f * s, cap = StrokeCap.Round))
        // 목 · 귀
        drawPath(p {
            moveTo(52f * s, 80f * s); lineTo(52f * s, 90f * s)
            quadraticBezierTo(60f * s, 95f * s, 68f * s, 90f * s)
            lineTo(68f * s, 80f * s); close()
        }, TutSkinDark)
        drawOval(TutSkinDark, topLeft = Offset(33.5f * s, 49f * s), size = Size(9f * s, 12f * s))
        drawOval(TutSkinDark, topLeft = Offset(77.5f * s, 49f * s), size = Size(9f * s, 12f * s))
        // 뒤통수
        drawOval(TutHair, topLeft = Offset(37f * s, 27f * s), size = Size(46f * s, 50f * s))
        drawPath(p {
            moveTo(35f * s, 56f * s)
            cubicTo(33f * s, 30f * s, 48f * s, 22f * s, 60f * s, 22f * s)
            cubicTo(72f * s, 22f * s, 87f * s, 30f * s, 85f * s, 56f * s)
            cubicTo(82f * s, 62f * s, 74f * s, 64f * s, 60f * s, 64f * s)
            cubicTo(46f * s, 64f * s, 38f * s, 62f * s, 35f * s, 56f * s)
            close()
        }, TutHair)
        // 머릿결
        drawPath(p {
            moveTo(48f * s, 30f * s); quadraticBezierTo(52f * s, 46f * s, 50f * s, 62f * s)
        }, TutHairDark, style = Stroke(width = 2f * s, cap = StrokeCap.Round))
        drawPath(p {
            moveTo(60f * s, 28f * s); quadraticBezierTo(62f * s, 46f * s, 60f * s, 64f * s)
        }, TutHairDark, style = Stroke(width = 2f * s, cap = StrokeCap.Round))
        drawPath(p {
            moveTo(72f * s, 30f * s); quadraticBezierTo(68f * s, 46f * s, 70f * s, 62f * s)
        }, TutHairDark, style = Stroke(width = 2f * s, cap = StrokeCap.Round))
        // 목덜미
        drawPath(p {
            moveTo(52f * s, 62f * s); quadraticBezierTo(60f * s, 68f * s, 68f * s, 62f * s); close()
        }, TutHairDark)
    }
}

/* 3단계 — 인식·추종: 펄스 링 + 점선 추종 경로 + 사용자 마커 + "인식 완료" 칩 */
@Composable
private fun OnbStepFollow(active: Boolean) {
    var chip by remember { mutableStateOf(false) }
    LaunchedEffect(active) {
        if (active) { chip = false; delay(1400); chip = true } else chip = false
    }
    val pulseT = rememberInfiniteTransition(label = "pulse")
    val phase by pulseT.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(2400, easing = LinearEasing), RepeatMode.Restart),
        label = "phase"
    )
    val pathProgress by animateFloatAsState(
        targetValue = if (active) 1f else 0f,
        animationSpec = tween(1800, easing = FastOutSlowInEasing), label = "path"
    )

    OnbStepFrame(
        title = "카트가 나를\n알아보고 따라와요",
        desc = "카메라로 사용자를 인식해\n자동으로 뒤따라 이동합니다",
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val cx = size.width / 2f
            val cy = size.height * 0.42f
            // 펄스 링 3개 (위상차)
            for (k in 0 until 3) {
                val p = (phase + k / 3f) % 1f
                drawCircle(
                    color = TutBlue.copy(alpha = (1f - p) * 0.5f),
                    radius = size.minDimension * (0.14f + p * 0.42f),
                    center = Offset(cx, cy),
                    style = Stroke(width = 2.5.dp.toPx())
                )
            }
            // 점선 추종 경로 (사용자 → 카트, progress 만큼 그려짐)
            val full = Path().apply {
                moveTo(size.width * 0.19f, size.height * 0.80f)
                quadraticBezierTo(
                    size.width * 0.56f, size.height * 0.74f,
                    cx, cy + size.minDimension * 0.22f
                )
            }
            val pm = PathMeasure().apply { setPath(full, false) }
            val seg = Path()
            pm.getSegment(0f, pm.length * pathProgress, seg, true)
            drawPath(
                seg, Color(0xFFE7C874),
                style = Stroke(
                    width = 4.dp.toPx(), cap = StrokeCap.Round,
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(9.dp.toPx(), 11.dp.toPx()))
                )
            )
        }
        // 사용자 마커
        Box(
            Modifier.align(Alignment.BottomStart).padding(start = 14.dp, bottom = 26.dp)
                .size(46.dp)
                .shadow(8.dp, CircleShape, spotColor = TutBlue.copy(alpha = 0.35f))
                .clip(CircleShape).background(TutMarkerBg),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Filled.Person, contentDescription = null, tint = Navy,
                modifier = Modifier.size(26.dp))
        }
        // 마스코트 (링 중앙)
        Box(Modifier.align(Alignment.Center).offset(y = (-16).dp)) {
            Mascot(width = 146.dp, mood = "idle", onLight = true)
        }
        // 인식 완료 칩
        androidx.compose.animation.AnimatedVisibility(
            visible = chip,
            enter = fadeIn() + slideInVertically { -it / 2 },
            exit = fadeOut(),
            modifier = Modifier.align(Alignment.TopCenter)
        ) {
            Row(
                Modifier
                    .shadow(8.dp, RoundedCornerShape(999.dp), spotColor = TutMint.copy(alpha = 0.5f))
                    .clip(RoundedCornerShape(999.dp)).background(TutMint)
                    .padding(horizontal = 14.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Filled.Check, contentDescription = null, tint = Color.White,
                    modifier = Modifier.size(14.dp))
                Spacer(Modifier.width(6.dp))
                Text("사용자 인식 완료", fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = Color.White)
            }
        }
    }
}

/* 4단계 — 결제·복귀: 카드 슬라이드인 → 체크 → 복귀 버튼 글로우 → 카트가 홈으로 복귀 */
@Composable
private fun OnbStepPay(active: Boolean) {
    // phase: 0 대기 · 1 카드인 · 2 체크 · 3 복귀버튼 강조 · 4 카트 복귀
    var phase by remember { mutableStateOf(0) }
    LaunchedEffect(active) {
        if (active) {
            phase = 0; delay(250); phase = 1; delay(800)
            phase = 2; delay(700); phase = 3; delay(900); phase = 4
        } else phase = 0
    }
    val cardX by animateDpAsState(
        if (phase >= 1) 0.dp else 230.dp,
        animationSpec = spring(dampingRatio = 0.75f, stiffness = Spring.StiffnessLow), label = "cardX"
    )
    val cardA by animateFloatAsState(if (phase >= 1) 1f else 0f, tween(350), label = "cardA")
    val checkScale by animateFloatAsState(
        if (phase >= 2) 1f else 0f,
        spring(dampingRatio = 0.5f, stiffness = Spring.StiffnessLow), label = "payCheck"
    )
    val cartX by animateDpAsState(
        if (phase >= 4) 84.dp else 0.dp,
        animationSpec = tween(1500, easing = FastOutSlowInEasing), label = "cartX"
    )
    val glowT = rememberInfiniteTransition(label = "glow")
    val glow by glowT.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1200, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "glowA"
    )

    OnbStepFrame(
        title = "여기서 바로\n결제하세요",
        desc = "계산대 줄 없이 간단하게 쇼핑 끝!\n앱에서 상품을 확인 후 바로 결제하고,\n카트는 복귀 버튼으로 반납해요",
    ) {
        // 결제 카드
        Column(
            Modifier.align(Alignment.TopCenter).padding(top = 12.dp)
                .offset(x = cardX).alpha(cardA)
                .width(196.dp)
                .shadow(16.dp, RoundedCornerShape(18.dp), spotColor = Navy.copy(alpha = 0.45f))
                .clip(RoundedCornerShape(18.dp))
                .background(Brush.linearGradient(listOf(Color(0xFF2A2E36), NavyDeep)))
                .padding(16.dp)
        ) {
            Text("CartPay 간편결제", color = Color.White.copy(alpha = 0.85f),
                fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(6.dp))
            Text("${won(19400)}원", color = Color.White,
                fontSize = 22.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.5).sp)
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(22.dp, 15.dp).clip(RoundedCornerShape(3.dp))
                    .background(Color(0xFFFFD34D)))
                Spacer(Modifier.width(6.dp))
                Text("신한카드 ····3204", color = Color.White.copy(alpha = 0.85f),
                    fontSize = 11.sp, fontWeight = FontWeight.Medium)
            }
        }
        // 결제 완료 체크
        Box(
            Modifier.align(Alignment.TopCenter).offset(x = 84.dp, y = (-2).dp)
                .size(48.dp).scale(checkScale)
                .shadow(10.dp, CircleShape, spotColor = TutMint.copy(alpha = 0.6f))
                .clip(CircleShape).background(TutMint),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Filled.Check, contentDescription = null, tint = Color.White,
                modifier = Modifier.size(26.dp))
        }
        // 홈(복귀 지점) 마커
        Box(
            Modifier.align(Alignment.BottomEnd).padding(bottom = 76.dp)
                .size(50.dp).clip(RoundedCornerShape(14.dp)).background(TutMarkerBg),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Filled.Home, contentDescription = null, tint = Navy,
                modifier = Modifier.size(26.dp))
        }
        // 홈으로 복귀하는 카트
        Box(Modifier.align(Alignment.BottomCenter).padding(bottom = 58.dp).offset(x = cartX)) {
            Mascot(width = 112.dp, mood = "idle", onLight = true)
        }
        // 영수증 · 복귀 버튼 (복귀 강조 글로우)
        Row(
            Modifier.align(Alignment.BottomCenter).fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Box(
                Modifier.weight(1f).height(46.dp)
                    .clip(RoundedCornerShape(13.dp)).background(Color(0xFFEEF2F8)),
                contentAlignment = Alignment.Center
            ) {
                Text("영수증", color = Color(0xFF7C879B), fontSize = 14.sp, fontWeight = FontWeight.Bold)
            }
            val glowing = phase >= 3
            Row(
                Modifier.weight(1.4f).height(46.dp)
                    .graphicsLayer {
                        if (glowing) { val sc = 1f + 0.04f * glow; scaleX = sc; scaleY = sc }
                    }
                    .shadow(if (glowing) (6 + 10 * glow).dp else 0.dp, RoundedCornerShape(13.dp),
                        ambientColor = TutBlue, spotColor = TutBlue)
                    .clip(RoundedCornerShape(13.dp))
                    .background(TutBlue),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Filled.Home, contentDescription = null, tint = Navy,
                    modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("복귀", color = Navy, fontSize = 14.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}

/* ============================================================
 *  SPLASH
 * ============================================================ */
@Composable
private fun SplashScreen(onDone: () -> Unit) {
    LaunchedEffect(Unit) { delay(2500); onDone() }
    Box(
        Modifier.fillMaxSize().background(Surface).clickable { onDone() },
        contentAlignment = Alignment.Center
    ) {
        // 은은한 앰버 장식 (모서리 포인트)
        Box(Modifier.align(Alignment.TopStart).offset(x = (-60).dp, y = (-70).dp)
            .size(200.dp).clip(CircleShape).background(Blue.copy(alpha = 0.08f)))
        Box(Modifier.align(Alignment.BottomEnd).offset(x = 60.dp, y = 70.dp)
            .size(180.dp).clip(CircleShape).background(Blue.copy(alpha = 0.10f)))

        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            // 노란 원 안에 중앙 정렬된 마스코트(다크 라인아트)
            Box(
                Modifier.size(156.dp)
                    .shadow(18.dp, CircleShape, spotColor = Blue.copy(alpha = 0.55f))
                    .clip(CircleShape).background(Blue),
                contentAlignment = Alignment.Center
            ) {
                Mascot(width = 112.dp, mood = "wave", onLight = true)
            }
            Spacer(Modifier.height(28.dp))
            // a3.png 로고 스타일 — 통통한 라운드체(Fredoka One) + 얇은 남색 외곽선 + 연한 옐로 그라데이션
            val bubbleFont = FontFamily(Font(com.example.R.font.fredoka_one))
            Box {
                // 외곽선 + 그림자 레이어 (얇고 연하게)
                Text("CartMe", fontSize = 46.sp, fontFamily = bubbleFont,
                    color = Color(0xFF3A4A6B),
                    style = TextStyle(
                        drawStyle = Stroke(width = 14f, join = StrokeJoin.Round, cap = StrokeCap.Round),
                        shadow = Shadow(color = Color(0xFF3A4A6B).copy(alpha = 0.18f),
                            offset = Offset(0f, 6f), blurRadius = 10f),
                    ))
                // 연한 옐로 그라데이션 채움 레이어
                Text("CartMe", fontSize = 46.sp, fontFamily = bubbleFont,
                    style = TextStyle(brush = Brush.verticalGradient(
                        listOf(Color(0xFFFFE9A3), Color(0xFFFFC94D)))))
            }
            Spacer(Modifier.height(10.dp))
            Text("나를 따라오는 스마트 카트", fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
                color = TextSub)
            Spacer(Modifier.height(16.dp))
            Box(Modifier.width(40.dp).height(4.dp).clip(CircleShape).background(Blue))
        }
        Text("탭하여 시작하기", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
            color = TextFaint,
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 54.dp))
    }
}

/* ============================================================
 *  LOGIN
 * ============================================================ */
@Composable
private fun LoginScreen(
    errorMessage: String,
    isLoading: Boolean,
    onLogin: (String, String) -> Unit,
    onSignUp: () -> Unit,
) {
    var email by remember { mutableStateOf("") }
    var pw    by remember { mutableStateOf("") }
    val focus = LocalFocusManager.current

    Box(Modifier.fillMaxSize().background(Surface)) {
        // 타이틀("다시 만나서\n반가워요", top 96dp)과 상단 높이를 맞춘다.
        Box(Modifier.align(Alignment.TopEnd).padding(top = 96.dp, end = 24.dp).width(118.dp)) {
            Mascot(width = 118.dp, mood = "idle", ring = Color(0xFFBFD8FF), onLight = true)
        }
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(start = 30.dp, end = 30.dp, top = 96.dp, bottom = 36.dp)
        ) {
            Text("다시 만나서\n반가워요", fontSize = 30.sp, fontWeight = FontWeight.Black, color = Navy,
                lineHeight = 40.sp, letterSpacing = (-0.5).sp)
            Spacer(Modifier.height(10.dp))
            Text("로그인하고 똑똑한 장보기를 시작해요", fontSize = 15.sp, fontWeight = FontWeight.Medium, color = TextSub)

            Spacer(Modifier.height(40.dp))
            AppInput(email, { email = it }, "이메일", keyboardType = KeyboardType.Email)
            Spacer(Modifier.height(14.dp))
            AppInput(pw, { pw = it }, "비밀번호", password = true)

            if (errorMessage.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
                Text(errorMessage, color = Danger, fontSize = 12.5.sp)
            }

            Spacer(Modifier.height(8.dp))
            Text("비밀번호를 잊으셨나요?", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = TextSub,
                modifier = Modifier.align(Alignment.End))

            Spacer(Modifier.height(36.dp))
            PrimaryButton(
                text = if (isLoading) "로그인 중..." else "로그인",
                enabled = !isLoading,
                onClick = { focus.clearFocus(); onLogin(email, pw) }
            )
            Spacer(Modifier.height(6.dp))
            Box(Modifier.fillMaxWidth().height(48.dp).clickable { onSignUp() }, contentAlignment = Alignment.Center) {
                Text("이메일로 회원가입", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = AmberInk)
            }
        }
    }
}

/* ============================================================
 *  SIGN-UP — 멀티스텝 위저드 (이름·휴대폰·이메일·비밀번호)
 * ============================================================ */
private data class SignupStep(
    val label: String, val placeholder: String, val type: KeyboardType,
    val password: Boolean, val title: String, val subtitle: String, val mood: String,
)

@Composable
private fun SignUpScreen(
    errorMessage: String,
    isLoading: Boolean,
    onSubmit: (String, String, String, String) -> Unit,
    onBack: () -> Unit,
) {
    val steps = remember {
        listOf(
            SignupStep("이름", "예) 김카트", KeyboardType.Text, false,
                "이름을\n알려주세요", "어떻게 불러드리면 될까요?", "wave"),
            SignupStep("휴대폰 번호", "010-0000-0000", KeyboardType.Phone, false,
                "연락처를\n입력해주세요", "주문 알림을 받을 번호예요 (선택)", "idle"),
            SignupStep("이메일", "you@example.com", KeyboardType.Email, false,
                "이메일을\n입력해주세요", "로그인할 때 사용할 이메일이에요", "idle"),
            SignupStep("비밀번호", "6자 이상 입력해주세요", KeyboardType.Password, true,
                "비밀번호를\n만들어주세요", "안전하게 설정해요", "celebrate"),
        )
    }
    var step  by remember { mutableStateOf(0) }
    var name  by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var pw    by remember { mutableStateOf("") }
    val focus = LocalFocusManager.current

    val values = listOf(name, phone, email, pw)
    val cur = steps[step]
    val canNext = when (step) {
        0 -> name.trim().isNotEmpty()
        1 -> true                                   // 휴대폰은 선택
        2 -> Regex(".+@.+\\..+").matches(email)
        else -> pw.length >= 6
    }
    val last = step == steps.lastIndex

    Box(Modifier.fillMaxSize().background(Blue)) {
        // 장식 원 (앰버 배경 위 톤다운)
        Box(Modifier.align(Alignment.TopEnd).offset(x = 70.dp, y = (-90).dp)
            .size(240.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.16f)))

        // 상단 바: 뒤로 + 단계 점
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 24.dp, end = 24.dp, top = 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                Modifier.size(40.dp).clip(CircleShape).background(Navy.copy(alpha = 0.12f))
                    .clickable { if (step > 0) step-- else onBack() },
                contentAlignment = Alignment.Center
            ) { Icon(Icons.Filled.ArrowBack, contentDescription = "뒤로", tint = Navy, modifier = Modifier.size(20.dp)) }
            Spacer(Modifier.width(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(7.dp), verticalAlignment = Alignment.CenterVertically) {
                steps.indices.forEach { i ->
                    val w by animateDpAsState(if (i == step) 24.dp else 8.dp, label = "dotw")
                    Box(Modifier.height(8.dp).width(w).clip(RoundedCornerShape(99.dp))
                        .background(if (i <= step) Navy else Navy.copy(alpha = 0.28f)))
                }
            }
        }

        // 패널 (타이틀 + 마스코트)
        Column(
            modifier = Modifier.fillMaxWidth().padding(top = 96.dp).padding(horizontal = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            AnimatedContent(targetState = step, label = "panel",
                transitionSpec = {
                    (slideInHorizontally { it / 3 } + fadeIn()) togetherWith
                        (slideOutHorizontally { -it / 3 } + fadeOut())
                }) { s ->
                val st = steps[s]
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(st.title, fontSize = 29.sp, fontWeight = FontWeight.Black, color = Navy,
                        lineHeight = 38.sp, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(10.dp))
                    Text(st.subtitle, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
                        color = Navy.copy(alpha = 0.65f), modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(18.dp))
                    Mascot(width = 190.dp, mood = st.mood, onLight = true)
                }
            }
        }

        // 하단 시트 (입력 + 다음) — 키보드가 올라오면 그 위로 밀어 올린다 (imePadding)
        Column(
            modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .clip(RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp)).background(Surface)
                // 키보드가 올라오면 시트를 그 위로 밀어 올린다. (배경은 키보드까지 이어지도록 imePadding 을 배경 뒤에 둔다)
                .imePadding()
                .padding(start = 30.dp, end = 30.dp, top = 28.dp, bottom = 38.dp)
        ) {
            Text(cur.label, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextSub)
            Spacer(Modifier.height(10.dp))
            AppInput(
                value = values[step],
                onValueChange = { v -> when (step) { 0 -> name = v; 1 -> phone = v; 2 -> email = v; else -> pw = v } },
                placeholder = cur.placeholder,
                password = cur.password,
                keyboardType = cur.type,
            )
            if (errorMessage.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                Text(errorMessage, color = Danger, fontSize = 12.sp)
            }
            Spacer(Modifier.height(16.dp))
            PrimaryButton(
                text = if (last) (if (isLoading) "가입 중..." else "가입 완료") else "다음",
                enabled = canNext && !isLoading,
                onClick = {
                    if (last) { focus.clearFocus(); onSubmit(name, phone, email, pw) }
                    else step++
                }
            )
        }
    }
}

/* ============================================================
 *  PAIR (대시보드 / QR 매칭) — 다크 네이비, 실제 QR + 타이머 + 재발급
 * ============================================================ */
@Composable
private fun PairScreen(
    uiState: CartUiState,
    onGenerateQR: () -> Unit,
    onLogout: () -> Unit,
    onFetchHistory: () -> Unit,
) {
    var showHistory by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize().background(ScreenBg)) {
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(start = 26.dp, end = 26.dp, top = 16.dp, bottom = 26.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically) {
                // 구매 내역 메뉴 버튼
                HistoryChip { onFetchHistory(); showHistory = true }
                Spacer(Modifier.width(8.dp))
                LogoutChip(onLogout)
            }
            Spacer(Modifier.height(6.dp))
            Text("카트로 연결하기", fontSize = 28.sp, fontWeight = FontWeight.Black, color = Navy,
                textAlign = TextAlign.Center)
            Spacer(Modifier.height(10.dp))
            Text(
                if (uiState.qrToken.isBlank()) "아래 버튼을 눌러 QR 코드를 만들어\n카트 카메라에 비춰주세요"
                else "매장 카트 손잡이의 카메라에\nQR을 비추면 바로 연결돼요",
                fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = TextSub,
                textAlign = TextAlign.Center, lineHeight = 21.sp
            )

            Spacer(Modifier.height(26.dp))
            // 흰색 QR 카드 — 진한 윤곽선 + 그림자 (목업 스타일)
            Box(
                Modifier
                    .shadow(14.dp, RoundedCornerShape(28.dp), spotColor = Navy.copy(alpha = 0.35f))
                    .clip(RoundedCornerShape(28.dp))
                    .background(Surface)
                    .border(2.dp, Navy, RoundedCornerShape(28.dp))
                    .padding(22.dp)
            ) {
                QrCodeImage(content = uiState.qrToken, size = 180.dp)
            }

            if (uiState.qrToken.isNotBlank()) {
                Spacer(Modifier.height(18.dp))
                var timeLeft by remember(uiState.qrToken) { mutableStateOf(180) }
                LaunchedEffect(uiState.qrToken) {
                    timeLeft = 180
                    while (timeLeft > 0) { delay(1000L); timeLeft-- }
                }
                val timeString = "%02d:%02d".format(timeLeft / 60, timeLeft % 60)
                val expired = timeLeft == 0
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Timer, contentDescription = null,
                        tint = if (expired) Danger else AmberInk, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(if (expired) "시간 만료 · 재발급이 필요해요" else "남은 시간 $timeString",
                        fontSize = 14.sp, fontWeight = FontWeight.Bold,
                        color = if (expired) Danger else AmberInk)
                }
                Spacer(Modifier.height(6.dp))
                Text("3분 내에 스캔해 주세요 · 스캔 시 자동 이동",
                    fontSize = 11.5.sp, color = TextSub, textAlign = TextAlign.Center)
            }

            Spacer(Modifier.weight(1f))
            Spacer(Modifier.height(24.dp))
            PrimaryButton(
                text = if (uiState.isLoading) "재발급 중..." else "QR 코드 재발급",
                enabled = !uiState.isLoading,
                onClick = onGenerateQR,
                leadingIcon = Icons.Filled.Refresh
            )
        }

        // 구매 내역 오버레이 — 헤더의 영수증(메뉴) 버튼으로 열기
        if (showHistory) {
            OrderHistoryPanel(uiState, onClose = { showHistory = false })
        }
    }
}

/* ============================================================
 *  SHOPPING — 장바구니는 socket:cart:updated 로 자동 갱신
 * ============================================================ */
@Composable
private fun ShoppingScreen(uiState: CartUiState, viewModel: CartViewModel, onCheckout: () -> Unit) {
    val count = uiState.shoppingList.sumOf { it.quantity }
    val total = uiState.shoppingList.sumOf { it.price * it.quantity }

    Box(Modifier.fillMaxSize().background(ScreenBg)) {
        Column(Modifier.fillMaxSize()) {
            // 헤더
            Row(modifier = Modifier.fillMaxWidth().padding(start = 22.dp, end = 18.dp, top = 14.dp, bottom = 4.dp),
                horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("나의 카트", fontSize = 26.sp, fontWeight = FontWeight.Black, color = Navy)
                    Spacer(Modifier.width(10.dp))
                    // 담김 개수 배지 — 상품 있으면 앰버 채움, 없으면 흰색 (목업)
                    Text("${count}개 담김", fontSize = 13.sp, fontWeight = FontWeight.ExtraBold, color = Navy,
                        modifier = Modifier.clip(RoundedCornerShape(99.dp))
                            .background(if (count > 0) Blue else Surface)
                            .border(1.5.dp, Navy, RoundedCornerShape(99.dp))
                            .padding(horizontal = 12.dp, vertical = 6.dp))
                }
                LogoutChip({ viewModel.logout() })
            }

            Column(modifier = Modifier.weight(1f).verticalScroll(rememberScrollState())
                .padding(horizontal = 22.dp)) {
                Spacer(Modifier.height(12.dp))
                CartControlCard(uiState,
                    onSet = { viewModel.setTrackingState(it) },
                    onReturn = { viewModel.completeOrder() })

                Spacer(Modifier.height(18.dp))
                Text("담은 상품 $count", fontSize = 14.sp, fontWeight = FontWeight.ExtraBold, color = Navy,
                    modifier = Modifier.padding(start = 4.dp))
                Spacer(Modifier.height(12.dp))

                if (uiState.shoppingList.isEmpty()) {
                    EmptyCart()
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        uiState.shoppingList.forEach { item ->
                            ItemRow(item) { viewModel.removeItem(item) }
                        }
                    }
                }
                Spacer(Modifier.height(16.dp))
            }

            // 하단 결제 시트 — 목업: 진한 테두리의 떠 있는 흰 카드
            Column(
                modifier = Modifier.fillMaxWidth()
                    .padding(horizontal = 14.dp)
                    .padding(bottom = 14.dp, top = 4.dp)
                    .shadow(10.dp, RoundedCornerShape(24.dp), spotColor = Navy.copy(alpha = 0.3f))
                    .clip(RoundedCornerShape(24.dp)).background(Surface)
                    .border(2.dp, Navy, RoundedCornerShape(24.dp))
                    .padding(horizontal = 20.dp, vertical = 16.dp)
            ) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("총 결제금액", fontSize = 15.sp, fontWeight = FontWeight.Medium, color = TextSub)
                    Text("${won(total)}원", fontSize = 24.sp, fontWeight = FontWeight.Black, color = Navy)
                }
                Spacer(Modifier.height(14.dp))
                PrimaryButton("결제하기", onCheckout, enabled = uiState.shoppingList.isNotEmpty(), height = 52.dp)
            }
        }
    }
}

/* ============================================================
 *  ORDER HISTORY — 구매 내역 (나의 카트 메뉴)
 * ============================================================ */
@Composable
private fun HistoryChip(onClick: () -> Unit) {
    Box(
        modifier = Modifier.size(40.dp).clip(RoundedCornerShape(12.dp))
            .background(Surface)
            .border(1.5.dp, Navy, RoundedCornerShape(12.dp))
            .clickable { onClick() },
        contentAlignment = Alignment.Center
    ) {
        Icon(Icons.Filled.ReceiptLong, contentDescription = "구매 내역",
            tint = Navy, modifier = Modifier.size(19.dp))
    }
}

// "2026-07-08T05:10:02.000Z" → "2026.07.08 14:10" (로컬 시간)
private fun formatOrderedAt(iso: String): String = runCatching {
    java.time.OffsetDateTime.parse(iso)
        .atZoneSameInstant(java.time.ZoneId.systemDefault())
        .format(java.time.format.DateTimeFormatter.ofPattern("yyyy.MM.dd HH:mm"))
}.getOrElse { iso.take(10) }

@Composable
private fun OrderHistoryPanel(uiState: CartUiState, onClose: () -> Unit) {
    BackHandler { onClose() }
    Box(Modifier.fillMaxSize().background(ScreenBg)) {
        Column(Modifier.fillMaxSize()) {
            // 헤더
            Row(
                modifier = Modifier.fillMaxWidth().padding(start = 8.dp, end = 22.dp, top = 14.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onClose) {
                    Icon(Icons.Filled.ArrowBack, contentDescription = "뒤로", tint = Navy, modifier = Modifier.size(22.dp))
                }
                Spacer(Modifier.width(2.dp))
                Text("구매 내역", fontSize = 26.sp, fontWeight = FontWeight.Black, color = Navy)
            }

            when {
                uiState.isHistoryLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("구매 내역을 불러오는 중...", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = TextSub)
                }
                uiState.orderHistory.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Filled.ReceiptLong, contentDescription = null, tint = TextFaint, modifier = Modifier.size(44.dp))
                        Spacer(Modifier.height(10.dp))
                        Text("아직 구매 내역이 없어요", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = TextSub)
                    }
                }
                else -> Column(
                    modifier = Modifier.weight(1f).verticalScroll(rememberScrollState())
                        .padding(horizontal = 22.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Spacer(Modifier.height(4.dp))
                    uiState.orderHistory.forEach { order -> OrderHistoryCard(order) }
                    Spacer(Modifier.height(16.dp))
                }
            }
        }
    }
}

@Composable
private fun OrderHistoryCard(order: OrderRecord) {
    Column(
        modifier = Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(RCard)).background(Surface)
            .border(1.5.dp, Navy, RoundedCornerShape(RCard))
            .padding(horizontal = 18.dp, vertical = 15.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text(formatOrderedAt(order.orderedAt), fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = TextSub)
            val statusLabel = when (order.paymentStatus) {
                "PAID", "COMPLETED" -> "결제 완료"
                else -> order.paymentStatus ?: ""
            }
            if (statusLabel.isNotBlank()) {
                Text(statusLabel, fontSize = 11.5.sp, fontWeight = FontWeight.ExtraBold, color = AmberInk,
                    modifier = Modifier.clip(RoundedCornerShape(99.dp)).background(BlueSoft)
                        .padding(horizontal = 10.dp, vertical = 4.dp))
            }
        }
        Spacer(Modifier.height(10.dp))
        order.items.forEach { item ->
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp),
                horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("${item.productName} × ${item.quantity}", fontSize = 13.5.sp,
                    fontWeight = FontWeight.SemiBold, color = Navy)
                Text("${won((item.unitPrice * item.quantity).toInt())}원", fontSize = 13.sp,
                    fontWeight = FontWeight.Bold, color = Navy)
            }
        }
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().height(1.dp).background(Line))
        Spacer(Modifier.height(10.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text("총 결제금액", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = TextSub)
            Text("${won(order.totalPrice.toInt())}원", fontSize = 17.sp, fontWeight = FontWeight.Black, color = Navy)
        }
    }
}

@Composable
private fun CartControlCard(uiState: CartUiState, onSet: (TrackingState) -> Unit, onReturn: () -> Unit) {
    val following = uiState.trackingState == TrackingState.FOLLOWING
    val tone: Color; val toneBg: Color; val icon: ImageVector; val label: String; val desc: String
    when (uiState.trackingState) {
        TrackingState.FOLLOWING -> { tone = AmberInk; toneBg = BlueSoft
            icon = Icons.Filled.NearMe; label = "자동 주행 중"; desc = "내 위치를 따라 이동하고 있어요" }
        TrackingState.PAUSED -> { tone = TextSub; toneBg = InputBg
            icon = Icons.Filled.Pause; label = "일시 정지"; desc = "추종 시작을 누르면 다시 따라가요" }
        TrackingState.LOST_TRACKING -> { tone = Color(0xFFE0A100); toneBg = Color(0x1FE0A100)
            icon = Icons.Filled.Shield; label = "사용자 인식 실패"; desc = "카트 정면 카메라 앞에 서주세요" }
        TrackingState.DISCONNECTED -> { tone = Danger; toneBg = Color(0x1AE5484D)
            icon = Icons.Filled.Shield; label = "통신 지연"; desc = "Wi-Fi 연결 상태를 확인해 주세요" }
    }

    Column(
        Modifier.fillMaxWidth()
            .shadow(8.dp, RoundedCornerShape(RCard), spotColor = Navy.copy(alpha = 0.25f))
            .clip(RoundedCornerShape(RCard)).background(Surface)
            .border(2.dp, Navy, RoundedCornerShape(RCard))
            .padding(16.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                PulsingDot(Green)
                Spacer(Modifier.width(4.dp))
                Text("${uiState.matchedCartId.ifBlank { "CART-01" }} 연결됨",
                    fontSize = 15.sp, fontWeight = FontWeight.ExtraBold, color = Navy)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.BatteryFull, contentDescription = null,
                    tint = if (uiState.cartBattery > 20) Green else Danger, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(4.dp))
                Text("${uiState.cartBattery}%", fontSize = 13.sp, fontWeight = FontWeight.Bold,
                    color = if (uiState.cartBattery > 20) Green else Danger)
            }
        }
        Spacer(Modifier.height(13.dp))
        // 상태 박스 — 목업: 앰버 소프트 배경 + 앰버 테두리, 밝은 앰버 아이콘 사각형 + 다크 아이콘
        val followingNow = uiState.trackingState == TrackingState.FOLLOWING
        Row(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(15.dp)).background(toneBg)
            .border(1.5.dp, if (followingNow) Blue else tone.copy(alpha = 0.35f), RoundedCornerShape(15.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(38.dp).clip(RoundedCornerShape(12.dp))
                .background(if (followingNow) Blue else tone)
                .then(if (followingNow) Modifier.border(1.5.dp, Navy, RoundedCornerShape(12.dp)) else Modifier),
                contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = null,
                    tint = if (followingNow) Navy else Color.White, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.width(11.dp))
            Column {
                Text(label, fontSize = 15.sp, fontWeight = FontWeight.ExtraBold, color = tone)
                Text(desc, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold, color = TextSub)
            }
        }
        Spacer(Modifier.height(11.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (following) {
                PrimaryButton("정지", { onSet(TrackingState.PAUSED) }, modifier = Modifier.weight(1f),
                    leadingIcon = Icons.Filled.Pause, variant = BtnVariant.Outline, height = 46.dp)
            } else {
                PrimaryButton("추종 시작", { onSet(TrackingState.FOLLOWING) }, modifier = Modifier.weight(1f),
                    leadingIcon = Icons.Filled.PlayArrow, height = 46.dp)
            }
            PrimaryButton("복귀", onReturn, modifier = Modifier.weight(1f),
                leadingIcon = Icons.Filled.Home, variant = BtnVariant.Outline, height = 46.dp)
        }
    }
}

@Composable
private fun ItemRow(item: CartItem, onRemove: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth()
        .shadow(6.dp, RoundedCornerShape(RCard), spotColor = Navy.copy(alpha = 0.2f))
        .clip(RoundedCornerShape(RCard)).background(Surface)
        .border(2.dp, Navy, RoundedCornerShape(RCard))
        .padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
        // 상품 아이콘 자리 — 목업: 앰버 소프트 사각형 + 다크 테두리 + 상품명 텍스트
        Box(Modifier.size(52.dp).clip(RoundedCornerShape(13.dp)).background(BlueSoft)
            .border(1.5.dp, Navy, RoundedCornerShape(13.dp)),
            contentAlignment = Alignment.Center) {
            Text(item.name.take(3), fontSize = 12.5.sp, fontWeight = FontWeight.ExtraBold, color = Navy)
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(item.name, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Navy,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("${item.id} · 수량 ${item.quantity}", fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                color = TextFaint, modifier = Modifier.padding(top = 3.dp))
        }
        Spacer(Modifier.width(8.dp))
        Text("${won(item.price * item.quantity)}원", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = Navy)
        Box(Modifier.size(34.dp).clip(RoundedCornerShape(9.dp)).clickable { onRemove() },
            contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.DeleteOutline, contentDescription = "삭제", tint = TextFaint, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun EmptyCart() {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        // 목업: 마스코트 라인아트 워터마크
        Box(Modifier.alpha(0.5f)) {
            Mascot(width = 150.dp, mood = "idle", onLight = true)
        }
        Spacer(Modifier.height(6.dp))
        Text("카트가 비어있어요", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = TextSub)
        Text("로봇 RFID가 상품을 자동 인식해요", fontSize = 12.5.sp, color = TextFaint)
    }
}

/* ============================================================
 *  PAYMENT
 * ============================================================ */
@Composable
private fun PaymentScreen(
    uiState: CartUiState,
    isLoading: Boolean,
    errorMessage: String,
    onPay: () -> Unit,
    onBack: () -> Unit,
) {
    val total = uiState.shoppingList.sumOf { it.price * it.quantity }

    Box(Modifier.fillMaxSize().background(ScreenBg)) {
        Column(Modifier.fillMaxSize()) {
            Row(modifier = Modifier.fillMaxWidth().padding(start = 14.dp, end = 20.dp, top = 14.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).clickable { onBack() },
                    contentAlignment = Alignment.Center) {
                    Icon(Icons.Filled.ArrowBack, contentDescription = "뒤로", tint = Navy, modifier = Modifier.size(22.dp))
                }
                Spacer(Modifier.width(4.dp))
                Text("결제하기", fontSize = 26.sp, fontWeight = FontWeight.Black, color = Navy)
            }

            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 24.dp)) {
                Spacer(Modifier.height(10.dp))
                Text("결제수단", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextSub,
                    modifier = Modifier.padding(start = 2.dp))
                Spacer(Modifier.height(10.dp))
                Row(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(RCard)).background(Surface)
                    .border(2.dp, Navy, RoundedCornerShape(RCard)).padding(18.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(46.dp).clip(RoundedCornerShape(13.dp)).background(Blue),
                        contentAlignment = Alignment.Center) {
                        Text("C", fontSize = 18.sp, fontWeight = FontWeight.Black, color = Navy)
                    }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text("CartPay 간편결제", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Navy)
                        Text("신한카드 ····3204", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = TextFaint,
                            modifier = Modifier.padding(top = 2.dp))
                    }
                    Box(Modifier.size(22.dp).clip(CircleShape).background(Blue), contentAlignment = Alignment.Center) {
                        Icon(Icons.Filled.Check, contentDescription = null, tint = Navy, modifier = Modifier.size(14.dp))
                    }
                }

                Spacer(Modifier.height(24.dp))
                Text("결제 금액", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextSub,
                    modifier = Modifier.padding(start = 2.dp))
                Spacer(Modifier.height(10.dp))
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(RCard)).background(Surface)
                    .border(2.dp, Navy, RoundedCornerShape(RCard)).padding(18.dp)) {
                    AmountRow("상품 금액", "${won(total)}원")
                    Spacer(Modifier.height(13.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("배송비", fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = TextSub)
                        Text("무료", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = AmberInk)
                    }
                    Spacer(Modifier.height(14.dp))
                    Box(Modifier.fillMaxWidth().height(1.dp).background(Line))
                    Spacer(Modifier.height(14.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically) {
                        Text("총 결제금액", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = Navy)
                        Text("${won(total)}원", fontSize = 22.sp, fontWeight = FontWeight.Black, color = AmberInk)
                    }
                }

                if (errorMessage.isNotBlank()) {
                    Spacer(Modifier.height(10.dp))
                    Text(errorMessage, color = Danger, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 2.dp))
                }
            }

            Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 34.dp, top = 8.dp)) {
                PrimaryButton(
                    text = if (isLoading) "결제 처리 중..." else "${won(total)}원 결제하기",
                    enabled = !isLoading,
                    onClick = onPay
                )
            }
        }
    }
}

@Composable
private fun AmountRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF5B6479))
        Text(value, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF5B6479))
    }
}

/* ============================================================
 *  COMPLETION — 컨페티 + 마스코트
 * ============================================================ */
@Composable
private fun CompletionScreen(uiState: CartUiState, onRestart: () -> Unit) {
    val total = uiState.shoppingList.sumOf { it.price * it.quantity }

    var popped by remember { mutableStateOf(false) }
    val pop by animateFloatAsState(if (popped) 1f else 0.8f,
        spring(dampingRatio = 0.45f, stiffness = Spring.StiffnessLow), label = "pop")
    LaunchedEffect(Unit) { popped = true }

    BoxWithConstraints(Modifier.fillMaxSize().background(NavyDeep)) {
        Confetti(maxWidth, maxHeight)

        Column(
            modifier = Modifier.fillMaxSize().padding(horizontal = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Box(Modifier.size(96.dp).scale(pop)
                .shadow(20.dp, CircleShape, spotColor = Blue.copy(alpha = 0.6f))
                .clip(CircleShape).background(Blue),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Check, contentDescription = null, tint = Navy, modifier = Modifier.size(54.dp))
            }
            Spacer(Modifier.height(26.dp))
            Text("결제 완료!", fontSize = 30.sp, fontWeight = FontWeight.Black, color = Color.White)
            Spacer(Modifier.height(8.dp))
            Text("${won(total)}원 결제되었어요", fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = LightBlue)
            Spacer(Modifier.height(14.dp))
            Mascot(width = 170.dp, mood = "celebrate")
            Spacer(Modifier.height(4.dp))
            Text("카트는 매장 반납대로 복귀하고 있어요", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                color = OnDarkSub)
            Spacer(Modifier.height(36.dp))
            PrimaryButton("처음으로", onRestart, variant = BtnVariant.Filled)
        }
    }
}

@Composable
private fun Confetti(areaW: Dp, areaH: Dp) {
    val colors = listOf(Color(0xFFF8C038), Color.White, Color(0xFFEF6B6B), Color(0xFF35C2A0))
    val t = rememberInfiniteTransition(label = "confetti")
    val prog by t.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(2600, easing = LinearEasing), RepeatMode.Restart),
        label = "fall"
    )
    Box(Modifier.fillMaxSize()) {
        repeat(14) { i ->
            val phase = (prog + i / 14f) % 1f
            val x = (6f + (i * 6.4f) % 88f) / 100f * areaW.value
            val y = phase * (areaH.value + 60f) - 40f
            val w = (8 + (i % 3) * 3).dp
            val h = (10 + (i % 2) * 6).dp
            Box(
                Modifier.offset(x = x.dp, y = y.dp).size(w, h)
                    .rotate(phase * 420f)
                    .alpha(((1f - phase) * 1.2f).coerceIn(0f, 1f))
                    .clip(RoundedCornerShape(3.dp))
                    .background(colors[i % 4])
            )
        }
    }
}
