document.addEventListener("DOMContentLoaded", () => {
    const logoContainer = document.getElementById('logoContainer');
    const mainLogo = document.getElementById('mainLogo');
    const voxelGrid = document.getElementById('voxelGrid');
    
    let isAnimating = false;

    logoContainer.addEventListener('click', () => {
        if (isAnimating) return; 
        isAnimating = true;

        // 1. Ocultar el logo original suavemente
        mainLogo.style.opacity = '0';

        // 2. Configuración de la rejilla
        // Ajusta esto si quieres cubos más grandes (menos número) o más pequeños (más número)
        const cols = 25; 
        const rows = 25; 
        
        voxelGrid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
        voxelGrid.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
        voxelGrid.innerHTML = ''; // Limpiar por si acaso

        // 3. Crear Canvas temporal
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        
        // Usamos las dimensiones reales de la imagen en pantalla
        const imgWidth = mainLogo.clientWidth;
        const imgHeight = mainLogo.clientHeight;
        
        canvas.width = imgWidth;
        canvas.height = imgHeight;
        
        // Dibujar la imagen en el canvas
        ctx.drawImage(mainLogo, 0, 0, imgWidth, imgHeight);

        // 4. Generar los cubos
        const widthStep = imgWidth / cols;
        const heightStep = imgHeight / rows;

        for (let y = 0; y < rows; y++) {
            for (let x = 0; x < cols; x++) {
                // Intentamos leer el color del píxel
                try {
                    const pixelData = ctx.getImageData(x * widthStep, y * heightStep, 1, 1).data;
                    const r = pixelData[0];
                    const g = pixelData[1];
                    const b = pixelData[2];
                    const alpha = pixelData[3];

                    // Si el píxel es muy transparente, no creamos cubo
                    if (alpha < 50) continue; 

                    const cube = document.createElement('div');
                    cube.classList.add('voxel-cube');
                    
                    // Asignar color
                    cube.style.backgroundColor = `rgba(${r}, ${g}, ${b}, 1)`;

                    voxelGrid.appendChild(cube);

                    // Retraso aleatorio LENTO (entre 0.2s y 1.8s)
                    const randomDelay = Math.random() * 1.5; 
                    const duration = 1.5 + Math.random() * 1.5; // Caída de 1.5s a 3s

                    setTimeout(() => {
                        cube.classList.add('falling');
                        cube.style.animationDuration = `${duration}s`;
                    }, randomDelay * 1000);

                } catch (e) {
                    console.error("Error leyendo píxel (posible problema de CORS si abres el archivo localmente):", e);
                    // Fallback: Si falla, creamos un cubo azul genérico para no romper la ilusión
                    const cube = document.createElement('div');
                    cube.classList.add('voxel-cube');
                    cube.style.backgroundColor = `#00aaff`; 
                    voxelGrid.appendChild(cube);
                    setTimeout(() => cube.classList.add('falling'), Math.random() * 1000);
                }
            }
        }
    });
});