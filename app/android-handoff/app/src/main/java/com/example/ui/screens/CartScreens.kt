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
import androidx.compose.ui.graphics.PathMeasure
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.drawscope.rotate as rotateDraw
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.viewmodel.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import androidx.compose.ui.graphics.ImageBitmap
import kotlin.math.abs

/* ============================================================
 *  CartMe · 디자인 토큰  (CartMe.dc.html 기반)
 * ============================================================ */
private val Blue        = Color(0xFF1F7BFF)   // primary
private val BlueSoft    = Color(0xFFE9F2FF)   // chip / soft accent
private val Navy        = Color(0xFF16224A)   // 본문 진한 텍스트
private val NavyDeep    = Color(0xFF0E1B33)   // 페어링 배경
private val ScreenBg    = Color(0xFFF5F8FC)   // 일반 화면 배경
private val Surface     = Color(0xFFFFFFFF)
private val InputBg     = Color(0xFFF5F8FC)
private val InputBorder = Color(0xFFEAEEF5)
private val TextSub     = Color(0xFF8A93A6)
private val TextFaint   = Color(0xFF9AA3B4)
private val Green       = Color(0xFF22C55E)
private val OnDarkSub   = Color(0xFF9FB2D6)
private val LightBlue   = Color(0xFFD7E8FF)
private val Danger      = Color(0xFFE5484D)
private val Line        = Color(0xFFEEF1F6)
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
        Screen.SPLASH, Screen.SIGNUP, Screen.COMPLETION -> Blue
        Screen.LOGIN, Screen.ONBOARDING -> Surface
        Screen.DASHBOARD -> NavyDeep
        Screen.SHOPPING, Screen.PAYMENT, Screen.SUPPORT -> ScreenBg
    }

    // 고객센터(챗봇)에서 뒤로가기 눌렀을 때 돌아갈 화면을 기억한다.
    var supportOrigin by remember { mutableStateOf(Screen.SHOPPING) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(screenBg)
            .padding(innerPadding)
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
                        onLogout = { viewModel.logout() }
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
            .border(1.dp, Line, RoundedCornerShape(32.dp))
            .clickable { onClick() }
            .padding(start = 7.dp, end = 18.dp, top = 7.dp, bottom = 7.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // 마스코트 아바타 + 온라인 표시
        Box(
            Modifier.size(46.dp).clip(CircleShape)
                .background(Brush.linearGradient(listOf(Color(0xFF3A86FF), Color(0xFF1B54C9)))),
            contentAlignment = Alignment.Center
        ) {
            Mascot(width = 32.dp, mood = "wave", ring = Color.White, mesh = Color(0xFFCFE2FF))
            Box(
                Modifier.align(Alignment.BottomEnd).offset(x = (-3).dp, y = (-3).dp)
                    .size(12.dp).clip(CircleShape).background(Green)
                    .border(2.dp, Surface, CircleShape)
            )
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

    Column(Modifier.fillMaxSize().background(ScreenBg)) {
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
) {
    // 둥실 떠오르는 idle 모션
    val floatT = rememberInfiniteTransition(label = "mascotFloat")
    val dy by floatT.animateFloat(
        initialValue = 0f, targetValue = -7f,
        animationSpec = infiniteRepeatable(tween(1400, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "dy"
    )
    // 손 흔들기
    val waveDeg by floatT.animateFloat(
        initialValue = 8f, targetValue = -22f,
        animationSpec = infiniteRepeatable(tween(700, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "wave"
    )
    val armExtra = when (mood) {
        "wave" -> waveDeg
        "celebrate" -> -46f
        else -> 0f
    }

    val height = width * (235f / 200f)
    Canvas(modifier = Modifier.size(width, height).offset(y = dy.dp)) {
        val sx = size.width / 200f
        val sy = size.height / 235f
        fun px(x: Float) = x * sx
        fun py(y: Float) = y * sy

        // handle (ring 곡선)
        val handle = Path().apply {
            moveTo(px(34f), py(70f))
            cubicTo(px(34f), py(44f), px(56f), py(42f), px(70f), py(42f))
        }
        drawPath(handle, ring, style = Stroke(width = 11f * sx, cap = StrokeCap.Round))

        // 왼팔
        rotateDraw(18f, pivot = Offset(px(44f), py(130f))) {
            drawRoundRect(Color.White, topLeft = Offset(px(34f), py(118f)),
                size = Size(20f * sx, 46f * sy), cornerRadius = CornerRadius(10f * sx, 10f * sy))
        }
        // 오른팔 (인사)
        rotateDraw(-18f + armExtra, pivot = Offset(px(156f), py(130f))) {
            drawRoundRect(Color.White, topLeft = Offset(px(146f), py(116f)),
                size = Size(20f * sx, 46f * sy), cornerRadius = CornerRadius(10f * sx, 10f * sy))
        }
        // 바구니 몸통
        drawRoundRect(Color.White, topLeft = Offset(px(46f), py(78f)),
            size = Size(108f * sx, 104f * sy), cornerRadius = CornerRadius(30f * sx, 30f * sy))
        // mesh
        drawLine(mesh, Offset(px(78f), py(92f)), Offset(px(78f), py(168f)), strokeWidth = 4f * sx, cap = StrokeCap.Round)
        drawLine(mesh, Offset(px(122f), py(92f)), Offset(px(122f), py(168f)), strokeWidth = 4f * sx, cap = StrokeCap.Round)
        drawLine(mesh, Offset(px(58f), py(150f)), Offset(px(142f), py(150f)), strokeWidth = 4f * sx, cap = StrokeCap.Round)
        // 볼
        drawOval(Cheek, topLeft = Offset(px(70f - 9f), py(132f - 6f)), size = Size(18f * sx, 12f * sy))
        drawOval(Cheek, topLeft = Offset(px(130f - 9f), py(132f - 6f)), size = Size(18f * sx, 12f * sy))
        // 눈
        drawOval(Navy, topLeft = Offset(px(83f - 6f), py(118f - 8.5f)), size = Size(12f * sx, 17f * sy))
        drawOval(Navy, topLeft = Offset(px(117f - 6f), py(118f - 8.5f)), size = Size(12f * sx, 17f * sy))
        drawCircle(Color.White, radius = 2f * sx, center = Offset(px(85f), py(115f)))
        drawCircle(Color.White, radius = 2f * sx, center = Offset(px(119f), py(115f)))
        // 미소
        val smile = Path().apply {
            moveTo(px(90f), py(134f))
            quadraticBezierTo(px(100f), py(144f), px(110f), py(134f))
        }
        drawPath(smile, Navy, style = Stroke(width = 4f * sx, cap = StrokeCap.Round))
        // 다리
        drawRoundRect(Color.White, topLeft = Offset(px(74f), py(180f)),
            size = Size(12f * sx, 20f * sy), cornerRadius = CornerRadius(6f * sx, 6f * sy))
        drawRoundRect(Color.White, topLeft = Offset(px(114f), py(180f)),
            size = Size(12f * sx, 20f * sy), cornerRadius = CornerRadius(6f * sx, 6f * sy))
        // 바퀴
        drawCircle(ring, radius = 14f * sx, center = Offset(px(80f), py(208f)))
        drawCircle(ring, radius = 14f * sx, center = Offset(px(120f), py(208f)))
        drawCircle(Color.White, radius = 5f * sx, center = Offset(px(80f), py(208f)))
        drawCircle(Color.White, radius = 5f * sx, center = Offset(px(120f), py(208f)))
    }
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
        BtnVariant.Filled  -> { container = Blue;    content = Color.White }
        BtnVariant.Outline -> { container = InputBg; content = Navy }
        BtnVariant.Light   -> { container = Color.White; content = Blue }
    }
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(height),
        shape = RoundedCornerShape(RBtn),
        elevation = if (variant == BtnVariant.Filled)
            ButtonDefaults.buttonElevation(defaultElevation = 8.dp, pressedElevation = 2.dp) else null,
        border = if (variant == BtnVariant.Outline)
            androidx.compose.foundation.BorderStroke(2.dp, InputBorder) else null,
        colors = ButtonDefaults.buttonColors(
            containerColor = container,
            contentColor = content,
            disabledContainerColor = Color(0xFFBFD3F2),
            disabledContentColor = Color.White
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
                Icon(Icons.Filled.VolumeUp, contentDescription = null, tint = Color.White, modifier = Modifier.size(17.dp))
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
            .then(if (onDark) Modifier else Modifier.border(1.dp, InputBorder, RoundedCornerShape(12.dp)))
            .clickable { onClick() },
        contentAlignment = Alignment.Center
    ) {
        Icon(Icons.Filled.ExitToApp, contentDescription = "로그아웃",
            tint = if (onDark) Color.White else TextSub, modifier = Modifier.size(19.dp))
    }
}

/* ============================================================
 *  ONBOARDING — 회원가입 직후 튜토리얼 (스크롤 연동 3단계)
 *    좌우로 스크롤(스와이프)하면 각 단계가 페이드로 전환된다.
 * ============================================================ */
private val DotIdle = Color(0xFFD7DEEA)

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun OnboardingScreen(onFinish: () -> Unit) {
    val pageCount = 3
    val pagerState = rememberPagerState(pageCount = { pageCount })
    val scope = rememberCoroutineScope()
    val isLast = pagerState.currentPage == pageCount - 1

    // 첫 진입 힌트: 한 번이라도 스크롤하면 사라진다.
    var hintDismissed by remember { mutableStateOf(false) }
    LaunchedEffect(pagerState) {
        snapshotFlow { pagerState.currentPageOffsetFraction }
            .collect { if (abs(it) > 0.02f) hintDismissed = true }
    }

    Box(Modifier.fillMaxSize().background(Surface)) {
        Column(Modifier.fillMaxSize()) {
            // 상단 바 · 건너뛰기
            Box(Modifier.fillMaxWidth().height(52.dp).padding(horizontal = 12.dp)) {
                androidx.compose.animation.AnimatedVisibility(
                    visible = !isLast,
                    enter = fadeIn(), exit = fadeOut(),
                    modifier = Modifier.align(Alignment.CenterEnd)
                ) {
                    Text(
                        "건너뛰기",
                        fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = TextSub,
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
                        1 -> OnbStepRecognize(active)
                        else -> OnbStepPay(active)
                    }
                }
            }

            // 점 인디케이터
            Row(
                Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 18.dp),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically
            ) {
                repeat(pageCount) { i ->
                    val selected = pagerState.currentPage == i
                    val w by animateDpAsState(if (selected) 24.dp else 8.dp, label = "dotW")
                    Box(
                        Modifier
                            .padding(horizontal = 4.dp)
                            .height(8.dp).width(w)
                            .clip(CircleShape)
                            .background(if (selected) Blue else DotIdle)
                    )
                }
            }

            // 다음 / 시작하기
            Box(Modifier.padding(start = 24.dp, end = 24.dp, bottom = 28.dp)) {
                PrimaryButton(
                    text = if (isLast) "시작하기" else "다음",
                    onClick = {
                        if (isLast) onFinish()
                        else scope.launch { pagerState.animateScrollToPage(pagerState.currentPage + 1) }
                    }
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
                Icon(Icons.Filled.SwipeLeft, contentDescription = null, tint = Blue,
                    modifier = Modifier.size(16.dp).offset(x = dx.dp))
                Spacer(Modifier.width(6.dp))
                Text("스크롤해서 둘러보기", fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = Blue)
            }
        }
    }
}

@Composable
private fun OnbStepFrame(
    art: @Composable BoxScope.() -> Unit,
    title: String,
    desc: String,
) {
    Column(
        modifier = Modifier.fillMaxSize().padding(horizontal = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Box(Modifier.size(280.dp), contentAlignment = Alignment.Center, content = art)
        Spacer(Modifier.height(28.dp))
        Text(title, fontSize = 23.sp, fontWeight = FontWeight.ExtraBold, color = Navy,
            textAlign = TextAlign.Center, lineHeight = 30.sp, letterSpacing = (-0.4).sp)
        Spacer(Modifier.height(12.dp))
        Text(desc, fontSize = 14.5.sp, fontWeight = FontWeight.Medium, color = TextSub,
            textAlign = TextAlign.Center, lineHeight = 22.sp)
    }
}

/* 1단계 — QR 스캔: 스캔 라인이 훑고, 끝나면 체크 팝업 */
@Composable
private fun OnbStepScan(active: Boolean) {
    var done by remember { mutableStateOf(false) }
    LaunchedEffect(active) {
        if (active) { done = false; delay(2200); done = true } else done = false
    }
    val scanT = rememberInfiniteTransition(label = "scan")
    val lineY by scanT.animateFloat(
        initialValue = 16f, targetValue = 156f,
        animationSpec = infiniteRepeatable(tween(1600, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "lineY"
    )
    val checkScale by animateFloatAsState(
        targetValue = if (done) 1f else 0f,
        animationSpec = spring(dampingRatio = 0.5f, stiffness = Spring.StiffnessLow), label = "checkScale"
    )

    OnbStepFrame(
        art = {
            Box(
                Modifier.size(190.dp)
                    .clip(RoundedCornerShape(28.dp))
                    .background(Surface)
                    .border(1.dp, InputBorder, RoundedCornerShape(28.dp)),
                contentAlignment = Alignment.Center
            ) {
                QrCodeImage(content = "CARTME-PAIR-ONBOARDING", size = 132.dp)
                // 코너 가이드
                ScanCorners()
                // 스캔 라인
                Box(
                    Modifier.fillMaxWidth().padding(horizontal = 18.dp)
                        .offset(y = (lineY - 95).dp).height(3.dp)
                        .clip(CircleShape)
                        .background(Brush.horizontalGradient(listOf(Color.Transparent, Blue, Color.Transparent)))
                        .alpha(if (done) 0f else 1f)
                )
                // 완료 체크
                Box(
                    Modifier.size(72.dp).scale(checkScale).clip(CircleShape).background(Green),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Filled.Check, contentDescription = null, tint = Color.White,
                        modifier = Modifier.size(38.dp))
                }
            }
        },
        title = "QR을 카트에 스캔해요",
        desc = "카트 손잡이의 QR 코드를 비추면\n나만의 스마트 카트와 연결돼요."
    )
}

@Composable
private fun ScanCorners() {
    Canvas(Modifier.size(160.dp)) {
        val s = 26f
        val w = 5f
        val pad = 6f
        val c = Blue
        fun corner(ox: Float, oy: Float, dx: Int, dy: Int) {
            drawLine(c, Offset(ox, oy), Offset(ox + dx * s, oy), strokeWidth = w, cap = StrokeCap.Round)
            drawLine(c, Offset(ox, oy), Offset(ox, oy + dy * s), strokeWidth = w, cap = StrokeCap.Round)
        }
        corner(pad, pad, 1, 1)
        corner(size.width - pad, pad, -1, 1)
        corner(pad, size.height - pad, 1, -1)
        corner(size.width - pad, size.height - pad, -1, -1)
    }
}

/* 2단계 — 사용자 인식: 펄스 링 + 경로선 + "인식 완료" 칩 */
@Composable
private fun OnbStepRecognize(active: Boolean) {
    var chip by remember { mutableStateOf(false) }
    LaunchedEffect(active) {
        if (active) { chip = false; delay(1300); chip = true } else chip = false
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
        art = {
            Canvas(Modifier.fillMaxSize()) {
                val cx = size.width / 2f
                val cy = size.height * 0.46f
                val base = size.minDimension * 0.16f
                // 펄스 링 3개 (위상차)
                for (k in 0 until 3) {
                    val p = (phase + k / 3f) % 1f
                    drawCircle(
                        color = Blue.copy(alpha = (1f - p) * 0.55f),
                        radius = base * (0.5f + p * 2.0f),
                        center = Offset(cx, cy),
                        style = Stroke(width = 4f)
                    )
                }
                // 이동 경로선 (progress 만큼 그려짐)
                val full = Path().apply {
                    moveTo(size.width * 0.2f, size.height * 0.86f)
                    cubicTo(
                        size.width * 0.35f, size.height * 0.66f,
                        size.width * 0.30f, size.height * 0.40f,
                        cx, cy
                    )
                }
                val pm = PathMeasure().apply { setPath(full, false) }
                val seg = Path()
                pm.getSegment(0f, pm.length * pathProgress, seg, true)
                drawPath(seg, Blue, style = Stroke(width = 5f, cap = StrokeCap.Round))
                if (pathProgress > 0.02f) {
                    val pos = pm.getPosition(pm.length * pathProgress)
                    drawCircle(Blue, radius = 6f, center = pos)
                }
            }
            Mascot(width = 140.dp, mood = "idle")
            // 인식 완료 칩
            androidx.compose.animation.AnimatedVisibility(
                visible = chip,
                enter = fadeIn() + slideInVertically { -it / 2 },
                exit = fadeOut(),
                modifier = Modifier.align(Alignment.TopCenter)
            ) {
                Row(
                    Modifier.clip(RoundedCornerShape(999.dp)).background(Blue)
                        .padding(horizontal = 14.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(Icons.Filled.Check, contentDescription = null, tint = Color.White,
                        modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("사용자 인식 완료", fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = Color.White)
                }
            }
        },
        title = "카트가 나를 알아보고 따라와요",
        desc = "카메라로 사용자를 인식해\n두 손 가볍게, 카트가 자동으로 따라와요."
    )
}

/* 3단계 — 결제·복귀: 카드 슬라이드인 → 체크 → 복귀 버튼 글로우 → 카트 복귀 */
@Composable
private fun OnbStepPay(active: Boolean) {
    // phase: 0 대기 · 1 카드인 · 2 체크 · 3 복귀버튼 강조 · 4 카트 복귀
    var phase by remember { mutableStateOf(0) }
    LaunchedEffect(active) {
        if (active) {
            phase = 0; delay(250); phase = 1; delay(750)
            phase = 2; delay(750); phase = 3; delay(1100); phase = 4
        } else phase = 0
    }
    val cardX by animateDpAsState(
        if (phase >= 1) 0.dp else 180.dp,
        animationSpec = spring(dampingRatio = 0.7f, stiffness = Spring.StiffnessLow), label = "cardX"
    )
    val checkScale by animateFloatAsState(
        if (phase >= 2) 1f else 0f,
        spring(dampingRatio = 0.5f, stiffness = Spring.StiffnessLow), label = "payCheck"
    )
    val cartX by animateDpAsState(
        if (phase >= 4) (-150).dp else 44.dp,
        animationSpec = tween(1500, easing = FastOutSlowInEasing), label = "cartX"
    )
    val glowT = rememberInfiniteTransition(label = "glow")
    val glow by glowT.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1200, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "glowA"
    )

    OnbStepFrame(
        art = {
            // 결제 카드
            Box(
                Modifier.align(Alignment.TopCenter).padding(top = 8.dp)
                    .offset(x = cardX)
                    .width(218.dp).height(130.dp)
                    .clip(RoundedCornerShape(18.dp))
                    .background(Brush.linearGradient(listOf(Color(0xFF3A86FF), Color(0xFF1B54C9))))
                    .padding(16.dp)
            ) {
                Text("CartPay · 신한카드", color = Color.White.copy(alpha = 0.9f),
                    fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Box(Modifier.align(Alignment.CenterStart).offset(y = 6.dp)
                    .size(30.dp, 22.dp).clip(RoundedCornerShape(5.dp))
                    .background(Brush.linearGradient(listOf(Color(0xFFFFE39A), Color(0xFFD9A93F)))))
                Column(Modifier.align(Alignment.BottomStart)) {
                    Text("${won(19400)}원", color = Color.White,
                        fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.5).sp)
                    Text("결제가 완료되었어요", color = Color.White.copy(alpha = 0.85f),
                        fontSize = 11.5.sp, fontWeight = FontWeight.Medium)
                }
            }
            // 결제 완료 체크
            Box(
                Modifier.align(Alignment.TopCenter).offset(y = 96.dp)
                    .size(54.dp).scale(checkScale).clip(CircleShape).background(Green),
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Filled.Check, contentDescription = null, tint = Color.White,
                    modifier = Modifier.size(28.dp))
            }
            // 복귀 버튼 (강조 글로우)
            val glowing = phase >= 3
            Row(
                Modifier.align(Alignment.Center).offset(y = 26.dp)
                    .graphicsLayer {
                        if (glowing) { val s = 1f + 0.05f * glow; scaleX = s; scaleY = s }
                    }
                    .shadow(if (glowing) (8 + 12 * glow).dp else 0.dp, RoundedCornerShape(14.dp),
                        ambientColor = Blue, spotColor = Blue)
                    .clip(RoundedCornerShape(14.dp))
                    .background(Blue)
                    .padding(horizontal = 22.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Filled.KeyboardReturn, contentDescription = null, tint = Color.White,
                    modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(8.dp))
                Text("제자리로 복귀", color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.Bold)
            }
            // 복귀하는 카트
            Box(Modifier.align(Alignment.BottomCenter).offset(x = cartX)) {
                Mascot(width = 92.dp, mood = "idle")
            }
        },
        title = "결제하면 카트가 스스로 복귀해요",
        desc = "CartPay로 간편하게 결제하고\n복귀 버튼만 누르면 제자리로 돌아가요."
    )
}

/* ============================================================
 *  SPLASH
 * ============================================================ */
@Composable
private fun SplashScreen(onDone: () -> Unit) {
    LaunchedEffect(Unit) { delay(2500); onDone() }
    Box(
        Modifier.fillMaxSize().background(Blue).clickable { onDone() },
        contentAlignment = Alignment.Center
    ) {
        // 장식 원
        Box(Modifier.align(Alignment.TopStart).offset(x = (-70).dp, y = (-80).dp)
            .size(260.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.10f)))
        Box(Modifier.align(Alignment.BottomEnd).offset(x = 50.dp, y = 60.dp)
            .size(220.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.08f)))

        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("CartMe", fontSize = 56.sp, fontWeight = FontWeight.Black, color = Color.White,
                letterSpacing = (-1).sp)
            Spacer(Modifier.height(8.dp))
            Text("스마트 카트로 더 가벼운 장보기", fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                color = LightBlue)
            Spacer(Modifier.height(18.dp))
            Mascot(width = 200.dp, mood = "wave")
        }
        Text("탭하여 시작하기", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
            color = Color.White.copy(alpha = 0.85f),
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
        Box(Modifier.align(Alignment.TopEnd).padding(top = 20.dp, end = 18.dp).width(118.dp)) {
            Mascot(width = 118.dp, mood = "idle", ring = Color(0xFFBFD8FF))
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
                Text("이메일로 회원가입", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Blue)
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
        // 장식 원
        Box(Modifier.align(Alignment.TopEnd).offset(x = 70.dp, y = (-90).dp)
            .size(240.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.09f)))

        // 상단 바: 뒤로 + 단계 점
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 24.dp, end = 24.dp, top = 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                Modifier.size(40.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.18f))
                    .clickable { if (step > 0) step-- else onBack() },
                contentAlignment = Alignment.Center
            ) { Icon(Icons.Filled.ArrowBack, contentDescription = "뒤로", tint = Color.White, modifier = Modifier.size(20.dp)) }
            Spacer(Modifier.width(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(7.dp), verticalAlignment = Alignment.CenterVertically) {
                steps.indices.forEach { i ->
                    val w by animateDpAsState(if (i == step) 24.dp else 8.dp, label = "dotw")
                    Box(Modifier.height(8.dp).width(w).clip(RoundedCornerShape(99.dp))
                        .background(if (i <= step) Color.White else Color.White.copy(alpha = 0.38f)))
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
                    Text(st.title, fontSize = 29.sp, fontWeight = FontWeight.Black, color = Color.White,
                        lineHeight = 38.sp, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(10.dp))
                    Text(st.subtitle, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = LightBlue,
                        modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(18.dp))
                    Mascot(width = 190.dp, mood = st.mood)
                }
            }
        }

        // 하단 시트 (입력 + 다음)
        Column(
            modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .clip(RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp)).background(Surface)
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
) {
    Box(Modifier.fillMaxSize().background(NavyDeep)) {
        Box(Modifier.align(Alignment.TopStart).offset(x = (-60).dp, y = (-70).dp)
            .size(200.dp).clip(CircleShape).background(Color(0x1F7FB4FF)))

        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(start = 30.dp, end = 30.dp, top = 20.dp, bottom = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                LogoutChip(onLogout, onDark = true)
            }
            Spacer(Modifier.height(8.dp))
            Text("카트로 연결하기", fontSize = 28.sp, fontWeight = FontWeight.Black, color = Color.White,
                textAlign = TextAlign.Center)
            Spacer(Modifier.height(10.dp))
            Text(
                if (uiState.qrToken.isBlank()) "아래 버튼을 눌러 QR 코드를 만들어\n카트 카메라에 비춰주세요"
                else "매장 카트 손잡이의 카메라에\nQR을 비추면 바로 연결돼요",
                fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = OnDarkSub,
                textAlign = TextAlign.Center, lineHeight = 21.sp
            )

            Spacer(Modifier.height(28.dp))
            // 흰색 QR 카드 (실제 QR)
            Box(Modifier.clip(RoundedCornerShape(28.dp)).background(Surface).padding(22.dp)) {
                QrCodeImage(content = uiState.qrToken, size = 180.dp)
            }

            if (uiState.qrToken.isNotBlank()) {
                Spacer(Modifier.height(16.dp))
                var timeLeft by remember(uiState.qrToken) { mutableStateOf(180) }
                LaunchedEffect(uiState.qrToken) {
                    timeLeft = 180
                    while (timeLeft > 0) { delay(1000L); timeLeft-- }
                }
                val timeString = "%02d:%02d".format(timeLeft / 60, timeLeft % 60)
                val expired = timeLeft == 0
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Timer, contentDescription = null,
                        tint = if (expired) Danger else LightBlue, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(if (expired) "시간 만료 · 재발급이 필요해요" else "남은 시간 $timeString",
                        fontSize = 14.sp, fontWeight = FontWeight.Bold,
                        color = if (expired) Danger else Color.White)
                }
                Spacer(Modifier.height(6.dp))
                Text("3분 내에 스캔해 주세요 · 스캔 시 자동 이동",
                    fontSize = 11.5.sp, color = OnDarkSub, textAlign = TextAlign.Center)
            }

            Spacer(Modifier.height(18.dp))
            Mascot(width = 128.dp, mood = "idle", ring = Color(0xFF3A5C99), mesh = Color(0xFF21345C))

            Spacer(Modifier.height(24.dp))
            PrimaryButton(
                text = if (uiState.isLoading) "재발급 중..." else "QR 코드 재발급",
                enabled = !uiState.isLoading,
                onClick = onGenerateQR,
                leadingIcon = Icons.Filled.Refresh
            )
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
                    Text("${count}개 담김", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = Blue,
                        modifier = Modifier.clip(RoundedCornerShape(99.dp)).background(BlueSoft)
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

            // 하단 결제 시트
            Column(
                modifier = Modifier.fillMaxWidth()
                    .clip(RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp)).background(Surface)
                    .padding(horizontal = 24.dp, vertical = 20.dp)
            ) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("총 결제금액", fontSize = 15.sp, fontWeight = FontWeight.Medium, color = TextSub)
                    Text("${won(total)}원", fontSize = 24.sp, fontWeight = FontWeight.Black, color = Navy)
                }
                Spacer(Modifier.height(16.dp))
                PrimaryButton("결제하기", onCheckout, enabled = uiState.shoppingList.isNotEmpty())
            }
        }
    }
}

@Composable
private fun CartControlCard(uiState: CartUiState, onSet: (TrackingState) -> Unit, onReturn: () -> Unit) {
    val following = uiState.trackingState == TrackingState.FOLLOWING
    val tone: Color; val toneBg: Color; val icon: ImageVector; val label: String; val desc: String
    when (uiState.trackingState) {
        TrackingState.FOLLOWING -> { tone = Blue; toneBg = BlueSoft
            icon = Icons.Filled.NearMe; label = "자동 주행 중"; desc = "내 위치를 따라 이동하고 있어요" }
        TrackingState.PAUSED -> { tone = TextSub; toneBg = InputBg
            icon = Icons.Filled.Pause; label = "일시 정지"; desc = "추종 시작을 누르면 다시 따라가요" }
        TrackingState.LOST_TRACKING -> { tone = Color(0xFFE0A100); toneBg = Color(0x1FE0A100)
            icon = Icons.Filled.Shield; label = "사용자 인식 실패"; desc = "카트 정면 카메라 앞에 서주세요" }
        TrackingState.DISCONNECTED -> { tone = Danger; toneBg = Color(0x1AE5484D)
            icon = Icons.Filled.Shield; label = "통신 지연"; desc = "Wi-Fi 연결 상태를 확인해 주세요" }
    }

    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(RCard)).background(Surface).padding(16.dp)) {
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
        Row(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(15.dp)).background(toneBg)
            .padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(38.dp).clip(RoundedCornerShape(12.dp)).background(tone),
                contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(20.dp))
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
    Row(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(RCard)).background(Surface)
        .padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(56.dp).clip(RoundedCornerShape(15.dp)).background(BlueSoft),
            contentAlignment = Alignment.Center) {
            Text(item.imageEmoji, fontSize = 26.sp)
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
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(Icons.Filled.ShoppingCart, contentDescription = null, tint = TextFaint, modifier = Modifier.size(40.dp))
        Spacer(Modifier.height(10.dp))
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
                    .border(2.dp, Blue, RoundedCornerShape(RCard)).padding(18.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(46.dp).clip(RoundedCornerShape(13.dp)).background(Blue),
                        contentAlignment = Alignment.Center) {
                        Text("C", fontSize = 18.sp, fontWeight = FontWeight.Black, color = Color.White)
                    }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text("CartPay 간편결제", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Navy)
                        Text("신한카드 ····3204", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = TextFaint,
                            modifier = Modifier.padding(top = 2.dp))
                    }
                    Box(Modifier.size(22.dp).clip(CircleShape).background(Blue), contentAlignment = Alignment.Center) {
                        Icon(Icons.Filled.Check, contentDescription = null, tint = Color.White, modifier = Modifier.size(14.dp))
                    }
                }

                Spacer(Modifier.height(24.dp))
                Text("결제 금액", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextSub,
                    modifier = Modifier.padding(start = 2.dp))
                Spacer(Modifier.height(10.dp))
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(RCard)).background(Surface).padding(18.dp)) {
                    AmountRow("상품 금액", "${won(total)}원")
                    Spacer(Modifier.height(13.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("배송비", fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF5B6479))
                        Text("무료", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Blue)
                    }
                    Spacer(Modifier.height(14.dp))
                    Box(Modifier.fillMaxWidth().height(1.dp).background(Line))
                    Spacer(Modifier.height(14.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically) {
                        Text("총 결제금액", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = Navy)
                        Text("${won(total)}원", fontSize = 22.sp, fontWeight = FontWeight.Black, color = Blue)
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

    BoxWithConstraints(Modifier.fillMaxSize().background(Blue)) {
        Confetti(maxWidth, maxHeight)

        Column(
            modifier = Modifier.fillMaxSize().padding(horizontal = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Box(Modifier.size(96.dp).scale(pop).clip(CircleShape).background(Color.White),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Check, contentDescription = null, tint = Blue, modifier = Modifier.size(54.dp))
            }
            Spacer(Modifier.height(26.dp))
            Text("결제 완료!", fontSize = 30.sp, fontWeight = FontWeight.Black, color = Color.White)
            Spacer(Modifier.height(8.dp))
            Text("${won(total)}원 결제되었어요", fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = LightBlue)
            Spacer(Modifier.height(14.dp))
            Mascot(width = 170.dp, mood = "celebrate")
            Spacer(Modifier.height(4.dp))
            Text("카트는 매장 반납대로 복귀하고 있어요", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                color = Color(0xFFBCD7FF))
            Spacer(Modifier.height(36.dp))
            PrimaryButton("처음으로", onRestart, variant = BtnVariant.Light)
        }
    }
}

@Composable
private fun Confetti(areaW: Dp, areaH: Dp) {
    val colors = listOf(Color(0xFFFFD64D), Color.White, Color(0xFF7FB4FF), Color(0xFFFF9DBB))
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
