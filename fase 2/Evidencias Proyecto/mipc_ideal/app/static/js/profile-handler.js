document.addEventListener('DOMContentLoaded', function() {
    // JavaScript para hacer clickeable el contenedor de perfil
    const profileContainer = document.querySelector('.profile-container');
    if (profileContainer) {
        profileContainer.addEventListener('click', function(e) {
            if (e.target.tagName !== 'A') {
                const link = this.querySelector('a');
                if (link) {
                    link.click();
                }
            }
        });
    }
});